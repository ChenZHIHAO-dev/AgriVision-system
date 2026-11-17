import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random

import numpy as np
from PIL import Image
import torch
from torch.utils.data import DataLoader, Dataset

from .model import build_model, preprocessing, ARCHITECTURES
from .inference import select_device


def metrics(matrix):
    matrix = np.asarray(matrix)
    tp = np.diag(matrix)
    recall = np.divide(tp, matrix.sum(1), out=np.zeros(len(tp), dtype=float), where=matrix.sum(1) != 0)
    precision = np.divide(tp, matrix.sum(0), out=np.zeros(len(tp), dtype=float), where=matrix.sum(0) != 0)
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros(len(tp), dtype=float), where=precision + recall != 0)
    return {"macro_f1": float(f1.mean()), "recall": recall.tolist(), "counts": matrix.sum(1).tolist(), "confusion_matrix": matrix.tolist()}


def read_manifest(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    groups = {}
    for row in rows:
        if row["split"] not in {"train", "val", "test"}:
            raise ValueError("Unknown dataset split")
        for key in (row["group"], row["sha256"]):
            if key in groups and groups[key] != row["split"]:
                raise ValueError("A source group or image appears in multiple splits")
            groups[key] = row["split"]
    return rows


class Images(Dataset):
    def __init__(self, root, rows, labels, size, training=False):
        self.root, self.rows, self.labels = root.resolve(), rows, labels
        self.transform = preprocessing(size, training)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        path = (self.root / row["path"]).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Image path escapes dataset root")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("Dataset image changed after manifest creation")
        with Image.open(path) as image:
            tensor = self.transform(image.convert("RGB"))
        return tensor, self.labels.index(row["label"])


@torch.inference_mode()
def evaluate_loader(model, loader, device, classes, max_batches=0):
    model.eval()
    matrix = np.zeros((classes, classes), dtype=int)
    for batch, (images, labels) in enumerate(loader):
        predictions = model(images.to(device)).argmax(1).cpu().numpy()
        for true, predicted in zip(labels.numpy(), predictions):
            matrix[int(true), int(predicted)] += 1
        if max_batches and batch + 1 >= max_batches:
            break
    return metrics(matrix)


def train(args):
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)
    device = select_device(args.device)
    config = json.loads(args.labels.read_text(encoding="utf-8"))
    labels = list(config["labels"])
    rows = read_manifest(args.manifest)
    if set(r["label"] for r in rows) != set(labels):
        raise ValueError("Manifest classes must exactly match the label configuration")
    loaders = {split: DataLoader(Images(args.data_root, [r for r in rows if r["split"] == split], labels, args.input_size, split == "train"), batch_size=args.batch_size, shuffle=split == "train", num_workers=0, pin_memory=device.type == "cuda") for split in ("train", "val")}
    if any(len(loader.dataset) == 0 for loader in loaders.values()):
        raise ValueError("Both train and val splits require images")
    model = build_model(args.architecture, len(labels), not args.no_pretrained).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=.01)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    best, stale, history = -1., 0, []
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = {"schema_version": 1, "crop": config["crop"], "architecture": args.architecture, "labels": labels, "label_names": config["labels"], "input_size": args.input_size, "normalization": "imagenet", "resize": "stretch", "version": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"), "threshold": .7, "margin": .12, "validated": False, "development_only": args.development_only or bool(args.max_batches), "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(), "seed": args.seed}
    for epoch in range(args.epochs):
        for parameter in model.features.parameters():
            parameter.requires_grad = epoch >= args.freeze_epochs
        model.train()
        if epoch < args.freeze_epochs:
            model.features.eval()
        losses = []
        for batch, (images, target) in enumerate(loaders["train"]):
            if len(images) < 2:
                continue
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                logits = model(images.to(device))
                loss = torch.nn.functional.cross_entropy(logits, target.to(device))
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.item()))
            if args.max_batches and batch + 1 >= args.max_batches:
                break
        report = evaluate_loader(model, loaders["val"], device, len(labels), args.max_batches)
        report.update({"epoch": epoch + 1, "loss": float(np.mean(losses)) if losses else None})
        history.append(report)
        print(json.dumps({"epoch": epoch + 1, "loss": report["loss"], "val_macro_f1": report["macro_f1"], "device": str(device)}), flush=True)
        if report["macro_f1"] > best:
            best, stale = report["macro_f1"], 0
            torch.save(model.state_dict(), args.output / "weights.pt")
            metadata["validation"] = report
            (args.output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            stale += 1
        if stale >= args.patience:
            break
    (args.output / "training.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    return metadata


def parser():
    result = argparse.ArgumentParser(description="Train a crop classifier from a grouped manifest")
    result.add_argument("--data-root", type=Path, required=True)
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--labels", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--architecture", choices=sorted(ARCHITECTURES), default="efficientnet_b0")
    result.add_argument("--epochs", type=int, default=30)
    result.add_argument("--batch-size", type=int, default=8)
    result.add_argument("--input-size", type=int, default=224)
    result.add_argument("--lr", type=float, default=3e-4)
    result.add_argument("--freeze-epochs", type=int, default=2)
    result.add_argument("--patience", type=int, default=5)
    result.add_argument("--seed", type=int, default=42)
    result.add_argument("--device", default="auto")
    result.add_argument("--no-pretrained", action="store_true")
    result.add_argument("--max-batches", type=int, default=0, help="Limit batches for pipeline checks only")
    result.add_argument("--development-only", action="store_true")
    return result


if __name__ == "__main__":
    args = parser().parse_args()
    if args.epochs < 1 or args.batch_size < 2 or args.input_size < 64:
        raise SystemExit("epochs >= 1, batch-size >= 2 and input-size >= 64 are required")
    train(args)
