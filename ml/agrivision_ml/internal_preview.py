"""用原始最终留出集验收既有识别候选，并单独导出管理员内测包。

原开发折权重/元数据不修改。新包保存来源身份、完整留出指标及明确内测阶段，
不声称重训了最终模型，不声称已验证国内田间，也不自动操作云端或鉴权。
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import numpy as np
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from .cross_validation import check_partition
from .evaluate import require_activation_metrics
from .experiment_report import save_confusion
from .external_report import digest, write_csv
from .inference import Predictor, rejection_indices
from .train import Images, metrics, read_manifest


def audit_original_split(source, original_manifest):
    """普通迁移训练的 train/val 拟合与选择已结束；只验收原始 test。

    与开发折模式不同，这里的训练元数据绑定完整清单，但拟合只能使用 train，
    选型和校准只能使用 val。read_manifest 会先拒绝路径、SHA 或分组跨子集。
    最终评估不调整分类头或拒识阈值，原候选包保持不变。
    """
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    if not metadata.get("crop") and metadata.get("task") != "crop_identification":
        raise ValueError("候选缺少识别任务身份")
    if metadata["manifest_sha256"] != digest(original_manifest):
        raise ValueError("候选的实际训练清单与原清单不同")
    rows = read_manifest(original_manifest)
    check_partition(rows, metadata["labels"])
    heldout = [row for row in rows if row["split"] == "test"]
    identity = {
        "source_bundle": str(source.resolve()),
        "source_weights_sha256": digest(source / "weights.pt"),
        "source_metadata_sha256": digest(source / "metadata.json"),
        "source_development_only": metadata.get("development_only", False),
        "original_manifest_sha256": digest(original_manifest),
        "evaluation_mode": "original_train_val_test",
        "holdout_images": len(heldout),
        "holdout_groups": len({row["group"] for row in heldout}),
        "overlap_path_sha_group": 0,
    }
    return metadata, heldout, identity


def audit_holdout(source, original_manifest, development_manifest):
    """开发折的训练、早停验证和外层选型数据，都不得包含原最终留出组。"""
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("task") != "crop_identification":
        raise ValueError("本入口只发布作物种类管理员预览")
    original, development = read_manifest(original_manifest), read_manifest(development_manifest)
    labels = metadata["labels"]
    check_partition(original, labels)
    check_partition(development, labels)
    if metadata["manifest_sha256"] != digest(development_manifest):
        raise ValueError("候选的实际训练清单与开发折不同")
    by_path = {row["path"]: row for row in original}
    for row in development:
        parent = by_path[row["path"]]
        if any(row[key] != parent[key] for key in ("label", "sha256", "group")):
            raise ValueError("开发折图片或分组与原清单不同")
    heldout = [row for row in original if row["split"] == "test"]
    for key in ("path", "sha256", "group"):
        if {row[key] for row in heldout} & {row[key] for row in development}:
            raise ValueError("原最终留出与开发数据交叉：" + key)
    identity = {"source_bundle": str(source.resolve()), "source_weights_sha256": digest(source / "weights.pt"),
                "source_metadata_sha256": digest(source / "metadata.json"),
                "source_development_only": metadata.get("development_only", False),
                "original_manifest_sha256": digest(original_manifest),
                "development_manifest_sha256": digest(development_manifest),
                "holdout_images": len(heldout), "holdout_groups": len({row["group"] for row in heldout}),
                "overlap_path_sha_group": 0}
    return metadata, heldout, identity


@torch.inference_mode()
def evaluate_holdout(args, metadata, rows, identity):
    """固定已有权重、温度与拒识参数，一次完整前向，不依据最终留出改模型。"""
    result_path = args.report / "evaluation.json"
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result["source_identity"] != identity:
            raise ValueError("该最终留出报告已属于不同候选，不能覆盖")
        return result
    predictor = Predictor(args.source, args.device)
    labels = predictor.labels
    dataset = Images(args.data_root, rows, labels, metadata["input_size"], resize=metadata.get("resize", "stretch"))
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)
    matrix = np.zeros((len(labels), len(labels)), dtype=int)
    predictions, offset = [], 0
    excluded = rejection_indices(metadata)
    for images, truth in tqdm(loader, desc="Original final holdout", unit="batch"):
        scores = (predictor.model(images.to(predictor.device)).float() / metadata.get("temperature", 1.)).softmax(1).cpu()
        top, indices = scores.topk(2, dim=1)
        for j, target in enumerate(truth.tolist()):
            row = rows[offset]
            predicted = int(indices[j, 0]); confidence = float(top[j, 0]); margin = float(top[j, 0] - top[j, 1])
            matrix[target, predicted] += 1
            predictions.append({"path": row["path"], "sha256": row["sha256"], "group": row["group"],
                                "true": labels[target], "predicted": labels[predicted], "correct": target == predicted,
                                "confidence": confidence, "margin": margin,
                                "accepted": predicted not in excluded and confidence >= metadata["threshold"] and margin >= metadata["margin"],
                                "scores": json.dumps(dict(zip(labels, scores[j].tolist())))})
            offset += 1
    result = metrics(matrix)
    accepted = [row for row in predictions if row["accepted"]]
    result.update({"labels": labels, "source_identity": identity, "images": len(rows),
                   "evaluation_scope": identity.get("evaluation_mode", "original_final_holdout_after_development_model_selection"),
                   "field_verified": False, "acceptance_rule": {"accuracy": .90, "macro_f1": .90,
                       "min_images_per_class": 20, "min_recall_per_class": .6},
                   "fixed_rejection_settings": {k: metadata.get(k, 1.) for k in ("threshold", "margin", "temperature")},
                   "selective": {"accepted": len(accepted), "coverage": len(accepted)/len(rows),
                       "accuracy": sum(row["correct"] for row in accepted)/len(accepted) if accepted else None},
                   "high_confidence_errors_0_9": sum(not row["correct"] and row["confidence"] >= .9 for row in predictions),
                   "code_sha256": {name: digest(Path(__file__).with_name(name)) for name in
                       ("internal_preview.py", "inference.py", "train.py", "augmentation.py", "model.py")}})
    try:
        require_activation_metrics(result)
    except ValueError as exc:
        result.update(internal_acceptance_passed=False, acceptance_failure=str(exc))
    else:
        result["internal_acceptance_passed"] = True
    args.report.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(args.report / "predictions.csv", predictions, list(predictions[0]))
    save_confusion(matrix, labels, args.report / "confusion.png")
    return result


def export_preview(source, output, result, report_path):
    """新建可追溯的预览发布物，不修改原开发包或伪装成正式田间发布。

    仅完整留出通过才默认启用。低于门槛的结果仍保留供讨论，本入口不自动放行。
    先写权重、最后写元数据；复制未完成的目录不会成为 Registry 的可用包。
    """
    require_activation_metrics(result)
    identity = result["source_identity"]
    if (digest(source / "metadata.json") != identity["source_metadata_sha256"]
            or digest(source / "weights.pt") != identity["source_weights_sha256"]):
        raise ValueError("评估后源模型改变，拒绝导出")
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    record = {"stage": "admin_internal_preview", "source_identity": identity,
              "source_version": metadata["version"], "evaluation_report_sha256": digest(report_path),
              "internal_acceptance_passed": True, "field_verified": False,
              "limitations": "使用固定候选权重的管理员内测发布；本步骤仅验收与导出，不重训，不代表国内田间验收。"}
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source / "weights.pt", output / "weights.pt")
    shutil.copy2(report_path, output / "evaluation-holdout.json")
    metadata.update(version=metadata["version"] + "-internal-preview-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                    validated=False, field_verified=False, development_only=False, development_ready=True,
                    release_stage="admin_internal_preview", internal_acceptance_passed=True,
                    source_development_only=identity["source_development_only"], preview_release=record,
                    test_report=result, weights_sha256=identity["source_weights_sha256"])
    (output / "release-record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--original-manifest", type=Path, required=True)
    parser.add_argument("--development-manifest", type=Path,
                        help="候选来自开发折时必填；原始 train/val/test 训练候选省略")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/models/crop-identification"))
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    torch.set_num_threads(2)
    if args.development_manifest:
        metadata, rows, identity = audit_holdout(args.source, args.original_manifest, args.development_manifest)
    else:
        metadata, rows, identity = audit_original_split(args.source, args.original_manifest)
    result = evaluate_holdout(args, metadata, rows, identity)
    print(json.dumps({k: result[k] for k in ("images", "accuracy", "macro_f1", "internal_acceptance_passed")}), flush=True)
    if args.export:
        export_preview(args.source, args.output, result, args.report / "evaluation.json")
        print("管理员内测包已准备：" + str(args.output), flush=True)


if __name__ == "__main__":
    main()
