"""实验评估入口。保存逐图预测、按来源的指标与混淆矩阵，数据集保持一份。"""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import torch
from torch.utils.data import DataLoader
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from tqdm import tqdm

from .inference import Predictor, rejection_indices
from .train import Images, metrics, read_manifest


def save_confusion(matrix, labels, output):
    """左边保留张数，右边按真实类别归一化，兼顾类别不平衡下的召回情况。"""
    matrix = np.asarray(matrix)
    recall = np.divide(matrix, matrix.sum(1, keepdims=True), out=np.zeros_like(matrix, dtype=float),
                       where=matrix.sum(1, keepdims=True) > 0)
    figure = Figure(figsize=(17, 7), dpi=150, layout="constrained")
    canvas = FigureCanvasAgg(figure)
    names = [name.removeprefix("wheat_").replace("_", " ") for name in labels]
    for axis, values, title in zip(figure.subplots(1, 2), (matrix, recall), ("Counts", "Recall by true class")):
        axis.imshow(values, cmap="Blues")
        axis.set(xticks=range(len(labels)), yticks=range(len(labels)),
                 xticklabels=names, yticklabels=names, xlabel="Predicted", ylabel="True", title=title)
        axis.tick_params(axis="x", rotation=60)
        for i, row in enumerate(values):
            for j, number in enumerate(row):
                text = str(int(number)) if title == "Counts" else f"{number:.0%}"
                axis.text(j, i, text, ha="center", va="center",
                          color="white" if number > values.max()*.55 else "#202020", fontsize=8)
    canvas.print_png(output)


@torch.inference_mode()
def report(bundle, data_root, manifest, split="val", device="cuda"):
    """一次前向同时生成总体、逐类、各来源统计，逐图 CSV 能回到具体照片复核。"""
    torch.set_num_threads(4)
    predictor = Predictor(bundle, device)
    metadata = predictor.metadata
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if digest != metadata["manifest_sha256"]:
        raise ValueError("评估清单与训练清单不同，请核对数据版本")
    rows = [row for row in read_manifest(manifest) if row["split"] == split]
    with (manifest.parent/"sources.csv").open(encoding="utf-8-sig", newline="") as stream:
        sources = {row["path"]: row["source"] for row in csv.DictReader(stream)}
    dataset = Images(data_root, rows, predictor.labels, metadata["input_size"],
                     resize=metadata.get("resize", "stretch"))
    loader = DataLoader(dataset, batch_size=16, num_workers=0)
    classes = len(predictor.labels)
    excluded = rejection_indices(metadata)
    matrix = np.zeros((classes, classes), dtype=int)
    by_source = defaultdict(lambda: np.zeros_like(matrix))
    predictions = []
    total_nll = 0.0
    offset = 0
    started = perf_counter()
    for images, truth in tqdm(loader, desc=f"Evaluate {split}", unit="batch"):
        # 与正式推理使用相同的温度、尺寸规则和类别顺序。
        logits = predictor.model(images.to(predictor.device)).float().cpu()
        scores = (logits / metadata.get("temperature", 1.0)).softmax(1)
        total_nll += torch.nn.functional.cross_entropy(logits, truth, reduction="sum").item()
        top_scores, indices = scores.topk(2, dim=1)
        for index, target in enumerate(truth.tolist()):
            row = rows[offset]
            source = sources[row["path"]]
            predicted = int(indices[index, 0])
            matrix[target, predicted] += 1
            by_source[source][target, predicted] += 1
            confidence = float(top_scores[index, 0])
            margin = float(top_scores[index, 0] - top_scores[index, 1])
            predictions.append({
                "path": row["path"], "source": source, "group": row["group"],
                "true": predictor.labels[target], "predicted": predictor.labels[predicted],
                "correct": target == predicted, "confidence": confidence,
                "accepted": predicted not in excluded and confidence >= metadata["threshold"] and margin >= metadata["margin"],
            })
            offset += 1
    result = metrics(matrix)
    accepted = [row for row in predictions if row["accepted"]]
    result.update({
        "split": split, "images": len(rows), "groups": len({row["group"] for row in rows}),
        "manifest_sha256": digest, "model_version": metadata["version"],
        "labels": predictor.labels, "nll": total_nll/len(rows),
        "sources": {key: metrics(value) for key, value in by_source.items()},
        "elapsed_seconds": perf_counter()-started,
        "selective": {"coverage": len(accepted)/len(rows), "accepted": len(accepted),
                      "accuracy": sum(row["correct"] for row in accepted)/max(len(accepted), 1)},
    })
    (bundle/f"evaluation-{split}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with (bundle/f"predictions-{split}.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(predictions[0]))
        writer.writeheader()
        writer.writerows(predictions)
    save_confusion(matrix, predictor.labels, bundle/f"confusion-{split}.png")
    print(json.dumps({key: result[key] for key in ("split", "images", "accuracy", "macro_f1", "nll")}), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="评估模型并导出逐图预测和混淆矩阵")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", choices=("val", "test"), default="val")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    report(args.bundle, args.data_root, args.manifest, args.split, args.device)
