"""固定线性头配方的田间数据加入对照：PV-only 与 PV+field。

只有训练数据构成改变：同一冻结 ImageNet 骨干、clean-only、C=0.1。
PV 验证和田间日期块验证逐图相同；原 PV 最终测试从未读入。
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import PIL
import torch
import torchvision
from torch.utils.data import DataLoader
from tqdm import tqdm

from . import linear_probe as probe
from .augmentation import preprocessing
from .cached_probe_cv import select_head
from .exif_diagnostic import ExifImages, audit_orientations
from .external_report import write_csv
from .model import build_model
from .train import read_manifest
from .experiment_report import save_confusion


def read_inputs(manifest, sources, baseline_manifest):
    """明确这是两类来源的开发清单；核对旧最终测试图片完全隔离。"""
    rows = read_manifest(manifest)
    with sources.open(encoding="utf-8-sig", newline="") as stream:
        origins = {row["path"]: row for row in csv.DictReader(stream)}
    if len({row["path"] for row in rows}) != len(rows):
        raise ValueError("开发清单重复引用图片")
    if set(origins) != {row["path"] for row in rows}:
        raise ValueError("来源表与训练清单不对应")
    merged = [{**origins[row["path"]], **row} for row in rows]
    if any(row["split"] not in {"train", "val"} for row in merged):
        raise ValueError("田间开发对照不接收最终 test")
    if {row["role"] for row in merged} != {"baseline", "field"}:
        raise ValueError("需要明确的 baseline 与 field 来源")
    heldout = {row["sha256"] for row in read_manifest(baseline_manifest) if row["split"] == "test"}
    if heldout & {row["sha256"] for row in merged}:
        raise ValueError("原最终测试照片进入了开发清单")
    labels = {row["label"] for row in merged}
    for role in ("baseline", "field"):
        for split in ("train", "val"):
            if {row["label"] for row in merged if row["role"] == role and row["split"] == split} != labels:
                raise ValueError("两来源各自训练/验证必须覆盖全部类别")
    return merged


def map_clean_features(data, cached_rows, target_rows, cached_root, target_root, labels):
    """原 fold1 的 train 首段为 clean，后两段是增强；严格只读取首段。

    此处 test 是旧交叉验证的开发外层折，不是原始最终 test。用绝对文件位置、
    原文件 SHA 与标签共同对齐，不能仅按行号或文件名假定对应。
    """
    lookup = {}
    for split in ("train", "val", "test"):
        selected = [row for row in cached_rows if row["split"] == split]
        x, y = data[split + "_x"], data[split + "_y"]
        if len(x) < len(selected) or len(y) != len(x):
            raise ValueError("旧缓存长度不对应")
        expected = np.array([labels.index(row["label"]) for row in selected])
        if not np.array_equal(y[:len(selected)], expected):
            raise ValueError("旧缓存 clean 标签顺序不对应")
        for i, row in enumerate(selected):
            path = (cached_root / row["path"]).resolve()
            if path in lookup:
                raise ValueError("旧缓存路径重复")
            lookup[path] = (row, x[i])
    vectors = []
    for row in target_rows:
        path = (target_root / row["path"]).resolve()
        original, vector = lookup[path]
        if original["sha256"] != row["sha256"] or original["label"] != row["label"]:
            raise ValueError("旧缓存与目标原图或标签不一致")
        vectors.append(vector)
    if len(target_rows) != len(lookup):
        raise ValueError("PV 开发清单与旧缓存的完整范围不同")
    return np.asarray(vectors, dtype=np.float32)


def reuse_pv(args, model, rows, labels):
    """复用原入口的全量 identity 检查；不改旧 sidecar，不绕过旧代码/骨干哈希。"""
    selected = [row for row in rows if row["role"] == "baseline"]
    orientation = audit_orientations(args.data_root, selected)
    if any(value not in (None, 1) for value in orientation.values()):
        raise ValueError("旧 PV 解码存在方向变化，必须重提固定特征")
    # 两个文件都存在才调用旧入口，以免缺文件时在原实验目录重新提取覆盖。
    if not all((args.reuse_probe / name).exists() for name in ("features.npz", "features.json")):
        raise ValueError("旧 PV 特征缓存不存在")
    cached_rows = read_manifest(args.reuse_manifest)
    old_args = SimpleNamespace(data_root=args.baseline_images, manifest=args.reuse_manifest,
                               labels=args.labels, architecture="convnext_tiny", input_size=320,
                               views=2, augmentation="light", seed=42, output=args.reuse_probe,
                               batch_size=args.batch_size)
    data = probe.feature_cache(old_args, model, cached_rows, labels)
    values = map_clean_features(data, cached_rows, selected, args.baseline_images, args.data_root, labels)
    return values, {"method": "strict_original_feature_cache_validation",
                    "source_sidecar_sha256": probe.digest(args.reuse_probe / "features.json"),
                    "source_npz_sha256": probe.digest(args.reuse_probe / "features.npz"),
                    "decoded_orientation_counts": dict(Counter(str(v) for v in orientation.values())),
                    "reused_clean_images": len(selected), "reused_augmented_images": 0}


@torch.inference_mode()
def encode_clean(args, model, rows):
    """田间原图先应用 EXIF，再用模型的固定 letterbox；不保存增强图。"""
    dataset = ExifImages(args.data_root, rows, preprocessing(320, resize="letterbox"))
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)
    vectors = []
    for images in tqdm(loader, desc="Field clean features", unit="batch"):
        vectors.append(model(images).cpu().numpy())
    return np.concatenate(vectors)


def feature_cache(args, model, rows, labels, recipe):
    path, sidecar = args.output / "features.npz", args.output / "features.json"
    probe.validate_source_images(args.data_root, rows)
    if path.exists() and sidecar.exists():
        saved = json.loads(sidecar.read_text(encoding="utf-8"))
        if saved["recipe"] != recipe or saved["cache_sha256"] != probe.digest(path):
            raise ValueError("田间特征缓存与固定实验身份不符")
        with np.load(path) as data:
            return data["features"], saved["provenance"]
    indices = {row["path"]: i for i, row in enumerate(rows)}
    pv_rows = [row for row in rows if row["role"] == "baseline"]
    field_rows = [row for row in rows if row["role"] == "field"]
    try:
        pv, provenance = reuse_pv(args, model, rows, labels)
    except (ValueError, KeyError) as exc:
        # 不修改旧缓存使其“通过”；明确记录失败原因，在本实验内重新提取 clean。
        provenance = {"method": "reencoded_pv_clean", "reason": str(exc), "reused_clean_images": 0}
        print("旧缓存不可复用，重新提取 PV clean：", exc, flush=True)
        pv = encode_clean(args, model, pv_rows)
    field = encode_clean(args, model, field_rows)
    features = np.empty((len(rows), pv.shape[1]), dtype=np.float32)
    for selected, vectors in ((pv_rows, pv), (field_rows, field)):
        for row, vector in zip(selected, vectors):
            features[indices[row["path"]]] = vector
    provenance["field_forward_images"] = len(field_rows)
    temporary = args.output / ".features.pending.npz"
    np.savez_compressed(temporary, features=features)
    temporary.replace(path)
    probe.write_json(sidecar, {"recipe": recipe, "cache_sha256": probe.digest(path),
                              "provenance": provenance,
                              "rows": [{k: row[k] for k in ("path", "sha256", "label", "split", "role")} for row in rows]})
    return features, provenance


def planned_conditions(rows, labels):
    """两组的实际 balanced 权重在前向前固定，避免看结果后改变来源比例。"""
    result = {}
    for name, roles in (("pv_only", {"baseline"}), ("pv_plus_field", {"baseline", "field"})):
        train = [row for row in rows if row["split"] == "train" and row["role"] in roles]
        counts = Counter(row["label"] for row in train)
        result[name] = {"training_images": len(train),
                        "train_counts": {label: counts[label] for label in labels},
                        "actual_class_weights": {label: len(train)/(len(labels)*counts[label]) for label in labels}}
    return result


def run(args):
    if (args.output / "comparison.json").exists():
        raise FileExistsError("固定田间对照已完成，不覆盖既有结果")
    torch.set_num_threads(args.threads)
    torch.manual_seed(42)
    config = json.loads(args.labels.read_text(encoding="utf-8-sig"))
    labels = list(config["labels"])
    field_plan = json.loads(args.manifest.with_name("recipe.json").read_text(encoding="utf-8"))
    if field_plan["manifest_sha256"] != probe.digest(args.manifest) or field_plan["validation_dates"] != ["2019-03-13"]:
        raise ValueError("田间开发划分与预先固定的日期方案不同")
    rows = read_inputs(args.manifest, args.manifest.with_name("sources.csv"), args.baseline_manifest)
    if set(labels) != {row["label"] for row in rows}:
        raise ValueError("类别表与数据清单不符")
    model = build_model("convnext_tiny", len(labels), pretrained=True).eval().requires_grad_(False)
    probe.replace_head(model, "convnext_tiny", torch.nn.Identity())
    # 先固定配方再开始前向，不依据验证结果调 C、增强强度或来源比例。
    code = [Path(__file__), Path(probe.__file__), Path(__file__).with_name("cached_probe_cv.py"),
            Path(__file__).with_name("exif_diagnostic.py"), Path(__file__).with_name("augmentation.py"),
            Path(__file__).with_name("model.py"), Path(__file__).with_name("train.py"),
            Path(__file__).parent / "preprocessing/images.py"]
    recipe = {
        "method": "frozen_imagenet_field_data_addition_clean_probe",
        "architecture": "convnext_tiny", "input_size": 320, "resize": "letterbox",
        "decode": "shared decode_rgb EXIF transpose", "extra_augmentation_views": 0,
        "C": .1, "source_weight_per_original_image": {"baseline": 1., "field": 1.},
        "class_weight_rule": "balanced; separately computed from each condition's train labels",
        "class_weight_limitation": "数据构成改变同时改变 balanced 类权重，不能解释为纯图片数量的因果效应。",
        "conditions": planned_conditions(rows, labels),
        "manifest_sha256": probe.digest(args.manifest), "sources_sha256": probe.digest(args.manifest.with_name("sources.csv")),
        "labels_sha256": probe.digest(args.labels), "baseline_manifest_sha256": probe.digest(args.baseline_manifest),
        "reuse_manifest_sha256": probe.digest(args.reuse_manifest),
        "backbone_sha256": probe.backbone_digest(model), "seed": 42,
        "torch": torch.__version__, "torchvision": torchvision.__version__, "pillow": PIL.__version__, "numpy": np.__version__,
        "code_sha256": {str(path.relative_to(Path(__file__).parent)): probe.digest(path) for path in code},
        "evaluation_role": "development_validation_PV_and_Pretoria_fixed_date",
        "validation_dates": ["2019-03-13"], "original_final_test_used": False, "export_release_bundle": False,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    recipe_path = args.output / "recipe.json"
    if recipe_path.exists() and json.loads(recipe_path.read_text(encoding="utf-8")) != recipe:
        raise ValueError("固定输出目录已属于另一套配方")
    probe.write_json(recipe_path, recipe)
    features, provenance = feature_cache(args, model, rows, labels, recipe)
    targets = np.array([labels.index(row["label"]) for row in rows])
    val_ids = np.array([i for i, row in enumerate(rows) if row["split"] == "val"])
    validation = (features[val_ids], targets[val_ids], [rows[i] for i in val_ids])
    comparison = {"recipe": recipe, "feature_provenance": provenance, "conditions": {}}
    for condition, roles in (("pv_only", {"baseline"}), ("pv_plus_field", {"baseline", "field"})):
        ids = np.array([i for i, row in enumerate(rows) if row["split"] == "train" and row["role"] in roles])
        training = (features[ids], targets[ids], [rows[i] for i in ids])
        # select_head 仅接收一个预先固定的 C，因此验证分数不用于挑超参数。
        classifier, search = select_head(training, validation, [.1], len(labels))
        counts = Counter(targets[ids].tolist())
        result = {"training_images": len(ids), "train_counts": {label: counts[i] for i, label in enumerate(labels)},
                  "actual_class_weights": {label: len(ids)/(len(labels)*counts[i]) for i, label in enumerate(labels)},
                  "fixed_C": .1, "converged": search[0]["converged"], "iterations": search[0]["iterations"],
                  "validation_by_source": {}}
        folder = args.output / condition
        folder.mkdir(exist_ok=True)
        weights, bias = probe.linear_weights(classifier)
        np.savez_compressed(folder / "head.npz", weights=weights, bias=bias)
        predictions = []
        scores = classifier.predict_proba(features[val_ids])
        for offset, i in enumerate(val_ids):
            predicted = int(np.argmax(scores[offset]))
            predictions.append({"path": rows[i]["path"], "sha256": rows[i]["sha256"],
                                "role": rows[i]["role"], "source": rows[i]["source"], "group": rows[i]["group"],
                                "true": rows[i]["label"], "predicted": labels[predicted],
                                "correct": predicted == targets[i], "uncalibrated_confidence": float(scores[offset,predicted]),
                                "scores": json.dumps(dict(zip(labels, scores[offset].tolist())))})
        write_csv(folder / "predictions.csv", predictions, list(predictions[0]))
        for role in ("baseline", "field"):
            chosen = np.array([i for i in val_ids if rows[i]["role"] == role])
            value = probe.prediction_metrics(targets[chosen], classifier.predict(features[chosen]), len(labels))
            result["validation_by_source"][role] = value
            save_confusion(np.array(value["confusion_matrix"]), labels, folder / f"confusion-{role}.png")
        probe.write_json(folder / "result.json", result)
        comparison["conditions"][condition] = result
        print(json.dumps({"condition": condition, "validation_by_source": result["validation_by_source"]}), flush=True)
    probe.write_json(args.output / "comparison.json", comparison)
    return comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/experiments/maize-field-development/manifest.csv"))
    parser.add_argument("--labels", type=Path, default=Path("data/maize/prepared/labels.json"))
    parser.add_argument("--baseline-manifest", type=Path, default=Path("data/maize/prepared/manifest.csv"))
    parser.add_argument("--baseline-images", type=Path, default=Path("data/maize/prepared/images"))
    parser.add_argument("--reuse-manifest", type=Path, default=Path("artifacts/experiments/maize-cv/folds/fold-1/manifest.csv"))
    parser.add_argument("--reuse-probe", type=Path, default=Path("artifacts/experiments/maize-linear-probe/convnext_tiny/fold-1"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/experiments/maize-field-development/linear-probe"))
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if args.batch_size < 1 or not 1 <= args.threads <= 2:
        parser.error("batch-size 必须为正数，CPU 线程限 1–2")
    run(args)


if __name__ == "__main__":
    main()
