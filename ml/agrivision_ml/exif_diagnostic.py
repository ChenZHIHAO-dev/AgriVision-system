"""EXIF 单因素对照：仅重新前向确实需要方向变换的图，其余沿用原逐图分数。

模型权重、温度、拒识阈值及类别次序全部与原诊断保持一致；不修改训练核心，
不重写原照片，不覆盖原评估。此对照仍是开发诊断，不是新的独立验收。
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image
import torch
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm

from .external_report import digest, read_external_rows, write_csv
from .experiment_report import save_confusion
from .inference import Predictor, rejection_indices
from .preprocessing.images import decode_rgb
from .train import metrics


ROTATED_ORIENTATIONS = {2, 3, 4, 5, 6, 7, 8}


def audit_orientations(root, rows):
    """读取真实原图头信息；不把无效方向值 0 错误解释成必须旋转。"""
    result = {}
    for row in rows:
        path = (root / row["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("图片越过数据根目录")
        with Image.open(path) as image:
            orientation = image.getexif().get(274)
        result[row["path"]] = orientation
    return result


def load_baseline(bundle, manifest, baseline, rows, metadata):
    """哈希与路径一一对应后才可复用未受方向影响的原分数。"""
    previous = json.loads((baseline / "evaluation.json").read_text(encoding="utf-8"))
    identities = {"weights_sha256": digest(bundle / "weights.pt"),
                  "model_metadata_sha256": digest(bundle / "metadata.json"),
                  "external_manifest_sha256": digest(manifest)}
    if any(previous.get(key) != value for key, value in identities.items()):
        raise ValueError("原诊断与本次模型/元数据/清单身份不同")
    labels = metadata["labels"]
    if previous["labels"] != labels:
        raise ValueError("类别顺序与原诊断不同")
    with (baseline / "predictions.csv").open(encoding="utf-8-sig", newline="") as stream:
        predictions = list(csv.DictReader(stream))
    by_path = {row["path"]: row for row in predictions}
    if len(by_path) != len(predictions) or set(by_path) != {row["path"] for row in rows}:
        raise ValueError("原诊断的逐图记录不完整或重复")
    scores = []
    for row in rows:
        saved = by_path[row["path"]]
        if saved["sha256"] != row["sha256"] or saved["true"] != row["label"]:
            raise ValueError("原图字节或标签已变化，不能复用分数")
        values = json.loads(saved["scores"])
        if set(values) != set(labels):
            raise ValueError("原诊断没有完整类别分数")
        ordered = np.asarray([values[label] for label in labels], dtype=float)
        if not np.isfinite(ordered).all() or (ordered < 0).any() or not np.isclose(ordered.sum(), 1., atol=1e-5):
            raise ValueError("原分数不是有效的概率分布")
        scores.append(ordered)
    return previous, by_path, np.asarray(scores)


class ExifImages(Dataset):
    """独立评估解码器。共享现有 decode_rgb，再用训练包声明的固定尺寸变换。"""
    def __init__(self, root, rows, transform):
        self.root, self.rows, self.transform = root, rows, transform

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        content = (self.root / row["path"]).read_bytes()
        import hashlib
        if hashlib.sha256(content).hexdigest() != row["sha256"]:
            raise ValueError("原图在对照期间变化")
        return self.transform(decode_rgb(content))


def summarize(scores, rows, metadata):
    labels = metadata["labels"]
    targets = np.array([labels.index(row["label"]) for row in rows])
    ordered = np.argsort(-scores, axis=1, kind="stable")
    top = ordered[:, 0]
    confidence = scores[np.arange(len(rows)), top]
    margin = confidence - scores[np.arange(len(rows)), ordered[:, 1]]
    accepted = ((confidence >= metadata["threshold"]) & (margin >= metadata["margin"])
                & ~np.isin(top, rejection_indices(metadata)))
    matrix = np.zeros((len(labels), len(labels)), dtype=int)
    np.add.at(matrix, (targets, top), 1)
    result = metrics(matrix)
    result["selective"] = {"accepted": int(accepted.sum()), "coverage": float(accepted.mean()),
                          "accuracy": float((top[accepted] == targets[accepted]).mean()) if accepted.any() else None}
    result["high_confidence_errors_0_9"] = int(((top != targets) & (confidence >= .9)).sum())
    return result, top, confidence, margin, accepted


@torch.inference_mode()
def report(bundle, data_root, manifest, baseline, output, *, batch_size=8, threads=2):
    if (output / "evaluation.json").exists():
        raise FileExistsError("EXIF 对照已存在，不重复前向或覆盖原实验")
    torch.set_num_threads(threads)
    metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    rows = read_external_rows(manifest, data_root, metadata["labels"])
    previous, by_path, original_scores = load_baseline(bundle, manifest, baseline, rows, metadata)
    orientation = audit_orientations(data_root, rows)
    changed_ids = [i for i, row in enumerate(rows) if orientation[row["path"]] in ROTATED_ORIENTATIONS]
    corrected_scores = original_scores.copy()
    started = perf_counter()
    if changed_ids:
        predictor = Predictor(bundle, "cpu")
        changed_rows = [rows[index] for index in changed_ids]
        dataset = ExifImages(data_root, changed_rows, predictor.transform)
        loader = DataLoader(dataset, batch_size=batch_size, num_workers=0, shuffle=False)
        offset = 0
        for images in tqdm(loader, desc="EXIF matched diagnostic", unit="batch"):
            values = (predictor.model(images).float() / float(metadata.get("temperature", 1.))).softmax(1).numpy()
            ids = changed_ids[offset:offset + len(values)]
            corrected_scores[ids] = values
            offset += len(values)
    original, old_top, *_ = summarize(original_scores, rows, metadata)
    corrected, new_top, confidence, margins, accepted = summarize(corrected_scores, rows, metadata)
    truth = np.array([metadata["labels"].index(row["label"]) for row in rows])
    result = {
        "evaluation_role": "external_development_exif_matched_diagnostic",
        "single_changed_factor": "EXIF orientation transposed before RGB resize; weights, temperature and gates unchanged",
        "images": len(rows), "forward_images": len(changed_ids),
        "reused_prediction_images": len(rows) - len(changed_ids),
        "orientation_counts": dict(Counter(str(value) for value in orientation.values())),
        "weights_sha256": previous["weights_sha256"], "model_metadata_sha256": previous["model_metadata_sha256"],
        "external_manifest_sha256": previous["external_manifest_sha256"],
        "baseline_predictions_sha256": digest(baseline / "predictions.csv"),
        "fixed_rejection_settings": {key: metadata.get(key, 1.) for key in ("threshold", "margin", "temperature")},
        "labels": metadata["labels"], "before": original, "after": corrected,
        "wrong_to_correct": int(((old_top != truth) & (new_top == truth)).sum()),
        "correct_to_wrong": int(((old_top == truth) & (new_top != truth)).sum()),
        "changed_top1": int((old_top != new_top).sum()),
        "elapsed_seconds": perf_counter() - started,
        "limitation": "已用于开发诊断；方向修正不能代替独立田间验证，不以此重新校准阈值或筛选错例。",
    }
    predictions = []
    for i, row in enumerate(rows):
        predictions.append({**by_path[row["path"]], "predicted": metadata["labels"][new_top[i]],
                            "correct": bool(new_top[i] == truth[i]), "confidence": float(confidence[i]),
                            "margin": float(margins[i]), "accepted": bool(accepted[i]),
                            "scores": json.dumps(dict(zip(metadata["labels"], corrected_scores[i].tolist()))),
                            "exif_orientation": orientation[row["path"]],
                            "forward_recomputed": i in changed_ids})
    output.mkdir(parents=True, exist_ok=True)
    if (output / "evaluation.json").exists():
        raise FileExistsError("EXIF 对照已存在，不覆盖原实验")
    (output / "evaluation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output / "predictions.csv", predictions, list(predictions[0]))
    write_csv(output / "errors.csv", sorted((row for row in predictions if not row["correct"]),
                                           key=lambda row: row["confidence"], reverse=True), list(predictions[0]))
    save_confusion(np.array(corrected["confusion_matrix"]), metadata["labels"], output / "confusion.png")
    print(json.dumps({key: result[key] for key in ("forward_images", "wrong_to_correct", "correct_to_wrong")}))
    print(json.dumps({"before_accuracy": original["accuracy"], "after_accuracy": corrected["accuracy"],
                      "before_macro_f1": original["macro_f1"], "after_macro_f1": corrected["macro_f1"]}))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if args.batch_size < 1 or args.threads < 1:
        parser.error("batch-size 和 threads 必须为正数")
    report(args.bundle, args.data_root, args.manifest, args.baseline, args.output,
           batch_size=args.batch_size, threads=args.threads)


if __name__ == "__main__":
    main()
