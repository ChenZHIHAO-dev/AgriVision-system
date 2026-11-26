"""田间来源只生成清单与审计，不复制图片，也不重划冻结的原工作集。

第一步默认只输出日期块可行性报告。人为明确 validation_dates 后才输出
训练清单；日期未知的照片暂缓，不能把它们随机分开来凑验证比例。
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from tqdm import tqdm

from .groups import _DisjointSets, group_capture_batches, group_duplicate_photos, separate_label_conflicts
from .images import fingerprint
from .tables import read_rows, write_rows


FIELDS = ("path", "label", "group", "sha256", "split")


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture_date(value):
    """EXIF 通常用冒号分隔日期；只保留日期，不把相机编号解释成植株身份。"""
    from datetime import datetime
    value = value.strip()[:10].replace(":", "-")
    if not value:
        return ""
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def load_inputs(root, baseline, external):
    """冻结工作图沿用原 split/group；田间源保留作者标签和原文件位置。"""
    root = root.resolve()
    source_rows = {row["path"]: row for row in read_rows(baseline.parent / "sources.csv")}
    existing, field = [], []
    for row in read_rows(baseline):
        original_path = row["path"]
        path = (baseline.parent / "images" / original_path).resolve()
        if not path.is_relative_to(root):
            raise ValueError("工作图不在项目根目录内")
        # 来源行可能也包含 group/split，但冻结清单是其最终边界的依据。
        merged = {**source_rows.get(original_path, {}), **row}
        merged.update(path=path.relative_to(root).as_posix(), role="baseline")
        existing.append(merged)
    supported = {row["label"] for row in existing}
    for row in read_rows(external):
        if row.get("review") not in {"keep", "review"}:
            raise ValueError("田间候选包含 hold/drop，请先处理来源审核")
        if row["label"] not in supported:
            raise ValueError("本次只接收冻结基线已支持的病害")
        if row.get("labels_json") and json.loads(row["labels_json"]) != [row["label"]]:
            raise ValueError("不能把混合病症直接转成单标签")
        path = (root / row["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("田间原图越过项目根目录")
        field.append({**row, "path": path.relative_to(root).as_posix(), "role": "field",
                      "capture_date": capture_date(row.get("capture_datetime", ""))})
    # 不改变文件，只读取方向归一的 dHash 和实际文件哈希。
    for row in tqdm(existing + field, desc="Audit field manifest", unit="image"):
        digest, dhash = fingerprint(root / row["path"])
        if row.get("sha256") and row["sha256"] != digest:
            raise ValueError(f"图片已变化：{row['path']}")
        row.update(sha256=digest, dhash=dhash)
    return existing, field


def reviewed_distinct_pairs(path, rows):
    """逐对视觉复核仅解除已确认的哈希误报；图像哈希变化后原复核自动失效。"""
    if path is None:
        return set()
    by_path = {row["path"]: row for row in rows}
    pairs = set()
    for record in read_rows(path):
        if record["decision"] != "different" or not record.get("reason"):
            raise ValueError("复核表需要 different 判断与具体理由")
        left, right = by_path[record["left"]], by_path[record["right"]]
        if left["role"] == right["role"]:
            raise ValueError("本入口只解除跨来源候选，不重划来源内部的冻结分组")
        if left["sha256"] != record["left_sha256"] or right["sha256"] != record["right_sha256"]:
            raise ValueError("复核图像哈希已变化")
        if left["sha256"] == right["sha256"]:
            raise ValueError("相同字节不能被标记为不同图片")
        pairs.add(frozenset((left["path"], right["path"])))
    return pairs


def release_reviewed_edges(clusters, distinct_pairs):
    """只重建含明确误报边的小候选组，其余公共查重结果原样保留。

    不改 dHash，也不放宽全局阈值；未被复核的近重复边仍保持连通。
    """
    result = []
    for cluster in clusters:
        paths = {row["path"] for row in cluster}
        if not any(pair <= paths for pair in distinct_pairs):
            result.append(cluster)
            continue
        sets = _DisjointSets(len(cluster))
        for i, left in enumerate(cluster):
            for j in range(i):
                right = cluster[j]
                exact = left["sha256"] == right["sha256"]
                near = (left["dhash"] ^ right["dhash"]).bit_count() <= 6
                pair = frozenset((left["path"], right["path"]))
                if exact or (near and pair not in distinct_pairs):
                    sets.union(i, j)
        components = defaultdict(list)
        for i, row in enumerate(cluster):
            components[sets.find(i)].append(row)
        result.extend(components.values())
    return result


def connect_field(existing, field, distinct_pairs=()):

    """同时查重，再合并完整拍摄日；缺少真实植株 ID 的局限继续保留。

    任何与基线照片相连的田间候选均排除，避免为了容纳新增图而移动旧 split。
    跨标签的近重复只进入待复核报告，不根据当前模型预测重标图片。
    """
    clusters = group_duplicate_photos(existing + field)
    clean, conflicts = separate_label_conflicts(release_reviewed_edges(clusters, distinct_pairs))
    conflicting = {path for group in conflicts for path in group}
    blocked = [{"path": row["path"], "reason": "cross_label_near_duplicate"}
               for row in field if row["path"] in conflicting]
    # 跨标签冲突涉及基线时保留原基线，报告而不静默重写冻结数据。
    field_clusters = []
    for cluster in clean:
        if any(row["role"] == "baseline" for row in cluster):
            blocked.extend({"path": row["path"], "reason": "overlaps_frozen_baseline"}
                           for row in cluster if row["role"] == "field")
        else:
            field_clusters.append(cluster)
    dates = {row["path"]: f"{row['source']}|date:{row['capture_date']}"
             for row in field if row["capture_date"]}
    clusters = group_capture_batches(field_clusters, dates)
    result = []
    for cluster in clusters:
        identifier = hashlib.sha256("|".join(sorted(row["sha256"] for row in cluster)).encode()).hexdigest()[:20]
        known_dates = sorted({row["capture_date"] for row in cluster if row["capture_date"]})
        # 无日期但与有日期照片近重复时沿用整个连通块；完全未知的块暂不训练。
        for row in cluster:
            result.append({**row, "group": f"field-{identifier}", "connected_dates": known_dates})
    return result, blocked, conflicts


def feasibility(rows, labels):
    blocks = defaultdict(list)
    for row in rows:
        blocks[row["group"]].append(row)
    counts = {label: {"images": 0, "known_date_blocks": 0, "dates": []} for label in labels}
    details = []
    for group, members in sorted(blocks.items()):
        dates = sorted({date for row in members for date in row["connected_dates"]})
        distribution = Counter(row["label"] for row in members)
        details.append({"group": group, "dates": dates, "counts": dict(distribution),
                        "split_identity": "conservative_date_block_not_verified_plant_id"})
        for label, count in distribution.items():
            counts[label]["images"] += count
            counts[label]["known_date_blocks"] += bool(dates)
            counts[label]["dates"].extend(dates)
    for value in counts.values():
        value["dates"] = sorted(set(value["dates"]))
    return {"by_label": counts, "blocks": details,
            "five_fold_field_feasible_by_block_count": all(v["known_date_blocks"] >= 5 for v in counts.values())}


def assign_development(existing, field, validation_dates):
    """只有显式选定日期才能划验证集。相近照片把多个日期相连时禁止拆开。"""
    validation_dates = set(validation_dates)
    available = {date for row in field for date in row["connected_dates"]}
    if not validation_dates or not validation_dates <= available:
        raise ValueError("验证日期须明确给出且在审计报告中存在")
    selected = []
    for row in field:
        dates = set(row["connected_dates"])
        if not dates:
            continue
        if dates & validation_dates and not dates <= validation_dates:
            raise ValueError("近重复照片连接了训练日和验证日，需整块选择验证日期")
        selected.append({**row, "split": "val" if dates <= validation_dates else "train"})
    labels = {row["label"] for row in existing}
    for split in ("train", "val"):
        if {row["label"] for row in selected if row["split"] == split} != labels:
            raise ValueError(f"田间 {split} 不覆盖全部类别；不能随机拆同日照片凑比例")
    # 旧最终 test 不进入新训练清单；其已消费身份另存报告，不称为新的独立验收集。
    combined = [dict(row) for row in existing if row["split"] != "test"] + selected
    return [{key: row[key] for key in FIELDS} for row in combined], combined


def build(root, baseline, external, output, *, validation_dates=(), overlap_review=None):
    if (output / "manifest.csv").exists():
        raise FileExistsError("实验清单已冻结，不覆盖其审计与划分")
    existing, field = load_inputs(root, baseline, external)
    distinct_pairs = reviewed_distinct_pairs(overlap_review, existing + field)
    connected, blocked, conflicts = connect_field(existing, field, distinct_pairs)
    labels = sorted({row["label"] for row in existing})
    report = {
        "evaluation_role": "field_development_only",
        "baseline_manifest_sha256": file_digest(baseline),
        "external_manifest_sha256": file_digest(external),
        "overlap_review_sha256": file_digest(overlap_review) if overlap_review else None,
        "reviewed_distinct_pairs": len(distinct_pairs),
        "baseline_images": len(existing), "field_input_images": len(field),
        "field_candidate_images": len(connected), "blocked_field": blocked,
        "near_duplicate_label_conflicts": conflicts,
        "excluded_baseline_original_test_images": sum(row["split"] == "test" for row in existing),
        "limitations": [
            "Pretoria 已用于外域开发诊断；后续任何子划分均不能恢复为未接触最终测试。",
            "按 EXIF 拍摄日保守合组，不等同于已核验的植株或田块身份。",
            "方向校正须与训练/服务共享解码一致；当前冻结训练核心尚未更改。",
            "仅生成小型清单，不复制、删除或修改原图；没有运行训练。",
        ],
        **feasibility(connected, labels),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "field-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if validation_dates:
        manifest, sources = assign_development(existing, connected, validation_dates)
        target = output / "manifest.csv"
        if target.exists():
            raise FileExistsError("实验清单已存在，不覆盖已冻结的实验身份")
        write_rows(target, FIELDS, manifest)
        source_fields = ("path", "label", "group", "split", "source", "license", "region",
                         "source_labels", "capture_date", "role")
        write_rows(output / "sources.csv", source_fields,
                   [{key: row.get(key, "") for key in source_fields} for row in sources])
        recipe = {"validation_dates": sorted(validation_dates), "data_root": ".",
                  "manifest_sha256": file_digest(target), "audit": report,
                  "training_enabled": False, "reason": "await shared EXIF decode fix and predefined GPU schedule"}
        (output / "recipe.json").write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation-dates", nargs="+", default=[])
    parser.add_argument("--overlap-review", type=Path)
    args = parser.parse_args()
    result = build(args.root, args.baseline, args.external, args.output,
                   validation_dates=[capture_date(value) for value in args.validation_dates],
                   overlap_review=args.overlap_review)
    print(json.dumps(result["by_label"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
