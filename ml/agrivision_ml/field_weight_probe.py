"""第三次田间开发对照：固定特征，只均衡来源与类别的训练权重。

这不是新的田间验收。前两次对照及其缓存只读；原 PV 最终 test 不参与。
每个“来源×类别”贡献相同总权重，不能再叠加 balanced 类权重。
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from threadpoolctl import threadpool_limits

from . import linear_probe as probe
from .experiment_report import save_confusion
from .external_report import write_csv
from .field_probe import read_inputs


def source_class_weights(rows, labels):
    """只查看 train 的来源和标签；权重总和保持为训练图数。

    若训练图共 N 张、有 S 个来源、K 个类别，则来源 s 的类别 k 每图权重为
    N / (S*K*n[s,k])。于是每个来源类别组合总权重都为 N/(S*K)。
    保持平均权重为 1，也避免同一 C 因任意整体放大权重而改变正则强度。
    """
    selected = [row for row in rows if row["split"] == "train"]
    roles = ("baseline", "field")
    counts = Counter((row["role"], row["label"]) for row in selected)
    if set(counts) != {(role, label) for role in roles for label in labels}:
        raise ValueError("两来源的训练部分必须都有完整类别")
    total_per_group = len(selected) / (len(roles) * len(labels))
    actual = {role: {label: total_per_group / counts[role, label] for label in labels} for role in roles}
    weights = np.array([actual[row["role"]][row["label"]] for row in selected], dtype=np.float64)
    return weights, {"training_images": len(selected), "total_weight_per_source_class": total_per_group,
                     "counts": {role: {label: counts[role, label] for label in labels} for role in roles},
                     "actual_sample_weights": actual, "total_weight": float(weights.sum()),
                     "class_weight": None}


def verified_features(folder, rows, recipe):
    """按缓存自身的原始记录核对身份，绝不修改旧哈希使新条件通过。

    原图的逐图 SHA 在 run 中另行核对。这里同时防止改标签、换行顺序、
    替换骨干记录、误用增强视图或替换 NPZ 而继续拟合旧特征。
    """
    sidecar = json.loads((folder / "features.json").read_text(encoding="utf-8"))
    expected = [{key: row[key] for key in ("path", "sha256", "label", "split", "role")} for row in rows]
    if sidecar["recipe"] != recipe or sidecar["rows"] != expected:
        raise ValueError("旧特征的配方或逐图身份与清单不一致")
    if sidecar["cache_sha256"] != probe.digest(folder / "features.npz"):
        raise ValueError("旧特征 NPZ 内容哈希不一致")
    with np.load(folder / "features.npz", allow_pickle=False) as cache:
        features = cache["features"]
    if features.ndim != 2 or len(features) != len(rows) or not np.isfinite(features).all():
        raise ValueError("旧特征矩阵尺寸或数值无效")
    return features


def fit_fixed_head(features, targets, weights):
    """只有一次 fit，没有验证集参数；C=0.1 是运行前固定的条件。

    sample_weight 已同时处理来源与类别。不再用 class_weight='balanced'，
    否则同一个少数类别会被重复校正，实验就不再是本次明确的权重规则。
    """
    classifier = LogisticRegression(C=.1, class_weight=None, max_iter=2000, tol=1e-4)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        classifier.fit(features, targets, sample_weight=weights)
    if any(issubclass(item.category, ConvergenceWarning) for item in caught):
        raise ValueError("固定均衡头未收敛，不写完成结果")
    return classifier


def run(args):
    if (args.output / "result.json").exists():
        raise FileExistsError("第三次开发对照已有结果，不覆盖")
    source_recipe = json.loads((args.features / "recipe.json").read_text(encoding="utf-8"))
    rows = read_inputs(args.manifest, args.manifest.with_name("sources.csv"), args.baseline_manifest)
    labels = list(json.loads(args.labels.read_text(encoding="utf-8-sig"))["labels"])
    identities = {"manifest_sha256": args.manifest, "sources_sha256": args.manifest.with_name("sources.csv"),
                  "labels_sha256": args.labels, "baseline_manifest_sha256": args.baseline_manifest}
    if any(source_recipe[key] != probe.digest(path) for key, path in identities.items()):
        raise ValueError("输入文件与旧特征配方不一致")
    if (source_recipe["architecture"] != "convnext_tiny" or source_recipe["extra_augmentation_views"] != 0
            or source_recipe["validation_dates"] != ["2019-03-13"] or source_recipe["original_final_test_used"]):
        raise ValueError("需要已冻结的 clean-only 日期块开发特征")
    # 骨干不重新加载；其真实权重摘要已绑定到原始缓存配方及 NPZ 摘要。
    # 同时核对原提取代码，发生变化时应单独审计，不能悄悄沿用新身份。
    for name, digest in source_recipe["code_sha256"].items():
        if probe.digest(Path(__file__).parent / name) != digest:
            raise ValueError("原特征提取代码已改变：" + name)
    if set(labels) != {row["label"] for row in rows}:
        raise ValueError("标签配置不对应")
    for key in ("group", "sha256"):
        train_values = {row[key] for row in rows if row["split"] == "train"}
        val_values = {row[key] for row in rows if row["split"] == "val"}
        if train_values & val_values:
            raise ValueError("训练验证出现交叉身份：" + key)
    probe.validate_source_images(args.data_root, rows)
    features = verified_features(args.features, rows, source_recipe)
    targets = np.array([labels.index(row["label"]) for row in rows])
    train_ids = np.array([i for i, row in enumerate(rows) if row["split"] == "train"])
    val_ids = np.array([i for i, row in enumerate(rows) if row["split"] == "val"])
    weights, weighting = source_class_weights(rows, labels)
    recipe = {"method": "third_development_comparison_source_class_balanced_head", "C": .1,
              "labels": labels, "weighting": weighting, "source_roles": ["baseline", "field"],
              "source_recipe_sha256": probe.digest(args.features / "recipe.json"),
              "source_sidecar_sha256": probe.digest(args.features / "features.json"),
              "source_features_sha256": probe.digest(args.features / "features.npz"),
              "source_backbone_sha256": source_recipe["backbone_sha256"],
              "source_manifest_sha256": probe.digest(args.manifest),
              "code_sha256": probe.digest(Path(__file__)),
              "evaluation_role": "third_development_comparison_same_PV_and_Pretoria_validation",
              "validation_dates": ["2019-03-13"], "original_final_test_used": False,
              "new_backbone_forward_images": 0, "export_release_bundle": False,
              "limitation": "已查看相同开发验证集的第三次机制对照，不是独立最终验收；分数未校准。"}
    args.output.mkdir(parents=True, exist_ok=True)
    recipe_path = args.output / "recipe.json"
    if recipe_path.exists() and json.loads(recipe_path.read_text(encoding="utf-8")) != recipe:
        raise ValueError("目标目录已有不同的固定配方")
    probe.write_json(recipe_path, recipe)
    # BLAS 也限线程；本实验只拟合小线性头，不与 GPU 争抢骨干训练。
    with threadpool_limits(limits=args.threads):
        classifier = fit_fixed_head(features[train_ids], targets[train_ids], weights)
        probabilities = classifier.predict_proba(features[val_ids])
    if not np.array_equal(classifier.classes_, np.arange(len(labels))):
        raise ValueError("拟合后的类别顺序不对应")
    head_weights, bias = probe.linear_weights(classifier)
    np.savez_compressed(args.output / "head.npz", weights=head_weights, bias=bias)
    predicted = probabilities.argmax(axis=1)
    result = {"recipe": recipe, "converged": True, "iterations": classifier.n_iter_.tolist(),
              "validation_by_source": {}}
    predictions = []
    for offset, i in enumerate(val_ids):
        predictions.append({"path": rows[i]["path"], "sha256": rows[i]["sha256"],
                            "role": rows[i]["role"], "source": rows[i]["source"], "group": rows[i]["group"],
                            "true": rows[i]["label"], "predicted": labels[predicted[offset]],
                            "correct": bool(predicted[offset] == targets[i]),
                            "uncalibrated_confidence": float(probabilities[offset].max()),
                            "scores": json.dumps(dict(zip(labels, probabilities[offset].tolist())))})
    write_csv(args.output / "predictions.csv", predictions, list(predictions[0]))
    for role in ("baseline", "field"):
        chosen = np.array([offset for offset, i in enumerate(val_ids) if rows[i]["role"] == role])
        value = probe.prediction_metrics(targets[val_ids[chosen]], predicted[chosen], len(labels))
        result["validation_by_source"][role] = value
        save_confusion(np.array(value["confusion_matrix"]), labels, args.output / f"confusion-{role}.png")
    probe.write_json(args.output / "result.json", result)
    print(json.dumps(result["validation_by_source"]), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/experiments/maize-field-development/manifest.csv"))
    parser.add_argument("--labels", type=Path, default=Path("data/maize/prepared/labels.json"))
    parser.add_argument("--baseline-manifest", type=Path, default=Path("data/maize/prepared/manifest.csv"))
    parser.add_argument("--features", type=Path, default=Path("artifacts/experiments/maize-field-development/linear-probe"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/experiments/maize-field-development/linear-probe/source-class-balanced"))
    parser.add_argument("--threads", type=int, choices=(1, 2), default=2)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
