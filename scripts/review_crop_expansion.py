"""整理已存在的玉米/花生扩类候选：引用原图，不复制图片、不修改 prepared。

作者标签先进入待筛表。采集植株身份未知时明确保留 unknown，不能把图片数量当独立植株数。
该表用于决定是否扩类；没有 keep 开关，不会隐式改变已冻结训练/测试数据。
"""
from __future__ import annotations
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.agrivision_ml.preprocessing.source_collection import (
    ROOT, audit_image, contact_sheet, save_json, write_csv,
)


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def peanut_candidates():
    """原始早斑/晚斑保留作者细标签；不能由旧混合 Leaf Spot 标签反推细类。"""
    rows = []
    base = ROOT / "data/peanut/sources/mendeley-22p2vcbxfk-v3/raw-agml"
    mapping = {"early_leaf_spot": "peanut_early_leaf_spot", "late leaf spot": "peanut_late_leaf_spot",
               "nutrition deficiency": "peanut_nutrient_deficiency_unspecified"}
    for item in read_csv(base / "images.csv"):
        if item["author_label"] not in mapping:
            continue
        path = base / item["path"]
        rows.append({"path": path.relative_to(ROOT).as_posix(), "label": mapping[item["author_label"]],
            "source": "mendeley-22p2vcbxfk-v3-raw-agml", "source_label": item["author_label"],
            "license": "CC BY 4.0", "region": "India, Karnataka, Koppal", "part": "leaf",
            "group": "unknown", "group_status": "capture_identity_unknown", "source_url": "https://data.mendeley.com/datasets/22p2vcbxfk/3",
            "decision": "", "review": "hold", "reason": "旧模型仅有合并叶斑类；按作者细类复核。营养不足是非病原异常，不能诊断具体缺素。",
            "width": item["width"], "height": item["height"], "pixel_sha256": item["decoded_rgb_sha256"],
            "sha256": item["sha256"], "error": ""})
    # PLANTHEAD 是独立肯尼亚来源，病原 EPPO 标记比网上的泛化病名更可追溯。
    base = ROOT / "data/peanut/sources/planthead-peanut-17053222/raw"
    mapping = {"MYCOAR": "peanut_early_leaf_spot", "MYCOBE": "peanut_late_leaf_spot", "PHOMAR": "peanut_web_blotch"}
    for folder in sorted(base.iterdir()):
        label = next((value for code, value in mapping.items() if code in folder.name), None)
        if not label or not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
                continue
            rows.append({"path": path.relative_to(ROOT).as_posix(), "label": label,
                "source": "planthead-peanut-17053222", "source_label": folder.name,
                "license": "CC BY 4.0", "region": "Kenya", "part": "leaf", "group": "unknown",
                "group_status": "capture_identity_unknown", "source_url": "https://zenodo.org/records/17053222",
                "decision": "", "review": "hold", "reason": "抽样均发现PDPs水印，整个来源暂不训练；不去水印。", **audit_image(path)})
    return rows


def maize_candidates():
    """只列新的确定候选/保留未定病名；共病图不硬塞单标签。"""
    rows = []
    for item in read_csv(ROOT / "data/maize/review/source-audit.csv"):
        if item["source"] != "mendeley-w56xxnykcc-v1" or item["source_label"] == "healthy":
            continue
        # 保留已有科学名和地块；common_rust 与页面 Southern Rust 的冲突不代作者解决。
        rows.append({**item, "decision": "", "review": "hold",
            "source_url": "https://data.mendeley.com/datasets/w56xxnykcc/1",
            "reason": item["reason"] or "小斑候选，先复核标签与水印；地块不能当成单株 ID。"})
    base = ROOT / "data/maize/sources/pretoria-field-20237613-v1"
    columns = ["GLS", "NCLB", "PLS", "CR", "SR", "NoFoliarSymptoms", "Other", "UnidentifiedDisease"]
    for item in read_csv(base / "metadata/Database.csv"):
        positives = [name for name in columns if int(item[name]) == 1]
        if not any(name in positives for name in ["PLS", "SR"]):
            continue
        path = base / "raw/leaf_images" / item["filePath"]
        single = len(positives) == 1
        label = {"PLS": "maize_phaeosphaeria_leaf_spot", "SR": "maize_southern_rust"}.get(positives[0], "") if single else ""
        rows.append({"path": path.relative_to(ROOT).as_posix(), "label": label,
            "source": "pretoria-field-20237613-v1", "source_label": "|".join(positives),
            "license": "CC BY 4.0", "region": "South Africa", "part": "leaf", "group": "unknown",
            "group_status": "capture_identity_unknown", "source_url": "https://doi.org/10.25403/UPresearchdata.20237613.v1",
            "decision": "", "review": "hold", "reason": "待单病标签质量复核" if single else "多标签共病，保留作者向量，禁止改为单病分类",
            "single_label": str(single).lower(), **{name: item[name] for name in columns}, **audit_image(path)})
    return rows


def write_candidates(crop, rows):
    """报告数量和抽样范围，不把少量目视抽查写成全库病理审核。"""
    folder = ROOT / "data" / crop / "review"
    # 不同来源有自己的元数据列，取字段并集，避免丢掉共病标签向量。
    fields = list(dict.fromkeys(key for row in rows for key in row))
    rows = [{key: row.get(key, "") for key in fields} for row in rows]
    write_csv(folder / "class-expansion-existing.csv", rows)
    by_class = defaultdict(list)
    for row in rows:
        if row["label"]:
            by_class[(row["source"], row["label"])].append(ROOT / row["path"])
    samples = {}
    for (source, label), paths in by_class.items():
        paths = sorted(paths)
        count = min(8, len(paths))
        selected = [paths[round(i * (len(paths) - 1) / max(1, count - 1))] for i in range(count)]
        samples[source + "/" + label] = contact_sheet(selected, folder / "expansion-samples" / (source + "-" + label + ".jpg"), label)
    quality_path = folder / "class-expansion-visual-review.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
    summary = {"rows": len(rows), "source_counts": dict(Counter(x["source"] for x in rows)),
        "class_counts": dict(Counter(x["label"] or "unmapped_or_multilabel" for x in rows)),
        "source_class_counts": dict(Counter(x["source"] + "/" + (x["label"] or "unmapped_or_multilabel") for x in rows)),
        "decode_failures": sum(bool(x.get("error")) for x in rows), "sampled_paths": samples,
        "visual_review": quality or "pending; separately record exact reviewed sample paths", "prepared_changed": False,
        "selection_note": "仅供扩类候选审计；所有hold；已作过开发外域诊断的来源若转训练须另找未看过的独立评估。"}
    save_json(folder / "class-expansion-existing.json", summary)
    print(crop, summary["rows"], summary["class_counts"], flush=True)


def main():
    write_candidates("peanut", peanut_candidates())
    write_candidates("maize", maize_candidates())


if __name__ == "__main__":
    main()
