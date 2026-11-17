import argparse
import hashlib
import json
from pathlib import Path

from torch.utils.data import DataLoader
from .inference import Predictor
from .train import Images, read_manifest, evaluate_loader


def evaluate(args):
    predictor = Predictor(args.bundle, args.device)
    metadata = predictor.metadata
    rows = [r for r in read_manifest(args.manifest) if r["split"] == args.split]
    if not rows:
        raise ValueError("No images in requested split")
    loader = DataLoader(Images(args.data_root, rows, metadata["labels"], metadata["input_size"]), batch_size=8)
    report = evaluate_loader(predictor.model, loader, predictor.device, len(metadata["labels"]))
    report.update({"split": args.split, "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(), "model_version": metadata["version"], "field_verified": args.field_verified})
    path = args.bundle / f"evaluation-{args.split}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.activate:
        if metadata.get("development_only") or args.split != "test" or not args.field_verified:
            raise ValueError("Activation requires a real model, test split and operator-confirmed field verification")
        if min(report["counts"]) < 20 or report["macro_f1"] < .8 or min(report["recall"]) < .6:
            raise ValueError("Development release gate requires >=20 test images/class, Macro-F1 >=.8 and each recall >=.6")
        metadata["validated"] = True
        metadata["test_report"] = report
        (args.bundle / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate a classifier and optionally activate a field-verified bundle")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", choices=["val", "test"], default="test")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--field-verified", action="store_true")
    print(json.dumps(evaluate(parser.parse_args()), indent=2))
