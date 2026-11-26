"""作物物种分类的统一筛选入口：先审核，再按观察组准备训练数据。

默认或 --check：同步唯一 species-review.csv，只统计，不复制照片。
--accept-source-labels：显式接纳来源标签用于内部基线，仍标注为未逐图人工审核。
--prepare：生成固定 data/crop-identification/prepared，已有工作集不会覆盖。
训练时才进行随机增强；本模块不下载图片、不生成 other 类、不启动训练。
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
import hashlib
import json
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from scripts.collect_crop_observations import allowed_license
from .crop_review import EXCLUDED_BASIS, INTERNAL_BASIS
from .review import read_selection
from .tables import read_rows, write_rows
from .wheat_review import SOURCE_FIELDS, build_dataset, print_report, print_selection

ROOT = Path(__file__).resolve().parents[3]
REVIEW_FIELDS = (
    "id", "decision", "label", "path", "source", "sha256", "group", "part", "note",
    "review_basis", "exclusion_reason", "source_label", "source_review",
    "scientific_name", "source_scientific_name", "source_url", "license",
    "author", "rights_holder", "country", "region", "observation_id",
    "gbif_occurrence", "dataset_key", "photo_url", "photo_page", "download_url",
    "download_variant", "catalogs", "original_path", "quality_grade", "captive",
    "source_media_id", "original_observation_id",
)
PROVENANCE_FIELDS = (
    "id", "review_basis", "source_label", "scientific_name", "source_scientific_name",
    "author", "rights_holder", "country", "region", "observation_id",
    "gbif_occurrence", "dataset_key", "photo_url", "photo_page",
    "download_url", "download_variant", "catalogs", "original_path",
    "quality_grade", "captive", "source_media_id", "original_observation_id",
)


def load_targets(root):
    """名称来自现有目标清单；目标清单不等于最终有足够图片的模型类别。"""
    config = json.loads((root / "configs/datasets/crop-identification.json").read_text(encoding="utf-8-sig"))
    if config.get("task") != "crop_identification":
        raise ValueError("目标配置的 task 必须是 crop_identification。")
    targets = {row["id"]: row for row in config["targets"]}
    if len(targets) != len(config["targets"]) or "other" in targets:
        raise ValueError("目标类别 ID 重复或包含没有真实图像依据的 other 类。")
    return targets


def photo_identity(row):
    """iNaturalist 尺寸和扩展名不同仍是同一张图，按官方照片数字 ID 归并。"""
    for field in ("photo_url", "photo_page"):
        parsed = urlparse(row.get(field, ""))
        known_host = parsed.hostname in {
            "inaturalist.org", "www.inaturalist.org", "static.inaturalist.org",
            "inaturalist-open-data.s3.amazonaws.com",
        }
        match = re.fullmatch(r"/photos/(\d+)(?:/[^/]*)?/?", parsed.path)
        if known_host and match:
            return "inat-photo:" + match[1]
    return row["id"]


def observation_identity(value):
    """GBIF 与 iNaturalist 可能仅协议或 www 不同，规范成同一个观察 URL。"""
    parsed = urlparse(value)
    match = re.fullmatch(r"/observations/(\d+)/?", parsed.path)
    if parsed.hostname in {"inaturalist.org", "www.inaturalist.org"} and match:
        return "https://www.inaturalist.org/observations/" + match[1]
    return value


def prior_decisions(rows):
    """旧筛选表升级为同图身份；同图的人工 drop 优先，备注合并保留。"""
    previous = {}
    for row in rows:
        identifier = photo_identity(row)
        if identifier not in previous:
            previous[identifier] = row
            continue
        old = previous[identifier]
        if old.get("label") != row.get("label"):
            raise ValueError(f"同图人工类别冲突，请先核对：{identifier}")
        rank = {"drop": 3, "keep": 2, "": 1}
        preferred = row if rank.get(row.get("decision", ""), 0) > rank.get(old.get("decision", ""), 0) else old
        previous[identifier] = {**preferred, "note": "\n".join(dict.fromkeys(
            value for value in (old.get("note"), row.get("note")) if value
        ))}
    return previous


def read_catalogs(review_root):
    """合并 GBIF/iNaturalist 清单；原图链接不同尺寸也不会重复计数。"""
    paths = sorted([*review_root.glob("gbif-*.csv"), *review_root.glob("inat-*.csv")])
    if not paths:
        raise FileNotFoundError(f"没有找到来源筛选表：{review_root} 中的 gbif-*.csv / inat-*.csv")
    grouped = defaultdict(list)
    required = ("id", "label", "path", "review", "license", "observation_id", "photo_url")
    for path in paths:
        for row in read_rows(path, required):
            if not row["id"]:
                raise ValueError(f"{path.name} 有缺少媒体 ID 的记录。")
            grouped[photo_identity(row)].append({
                **row, "source": path.stem, "catalog": path.name,
                "source_media_id": row["id"],
                "original_observation_id": row["observation_id"],
                "observation_id": observation_identity(row["observation_id"]),
            })
    return grouped


def excluded_taxon(row, target):
    """核对来源学名及配置排除项，尤其避免把野大豆归入栽培大豆。"""
    source_name = " ".join(row.get("source_scientific_name", "").casefold().split())
    expected = target["scientific_name"].casefold()
    if source_name.split()[:2] != expected.split()[:2]:
        return "来源学名与目标栽培物种不符或缺少来源学名"
    for taxon in target.get("excluded_taxa", []):
        excluded = " ".join(taxon.casefold().split())
        # 学名作者有时插在种名和亚种之间，rank + epithet 仍必须被排除。
        suffix = " ".join(excluded.split()[2:])
        if source_name.startswith(excluded) or (suffix and suffix in source_name):
            return "配置明确排除的野生或非目标分类单元：" + taxon
    return ""


def source_exclusion(row, targets, root):
    """硬性来源条件不能被实验开关或旧 keep 绕过；错误保留在筛选表内。"""
    if row.get("review", "").strip().lower() in {"drop", "hold"}:
        return row.get("reason") or "原来源表已排除"
    target = targets.get(row.get("label"))
    if not target:
        return "来源类别未登记到当前物种目标清单"
    reason = excluded_taxon(row, target)
    if reason:
        return reason
    license_url = row.get("license", "")
    if urlparse(license_url).scheme not in {"http", "https"} or not allowed_license(license_url):
        return "逐图许可不在 CC0 / CC BY / CC BY-SA 允许范围"
    if "/licenses/" in license_url and not (row.get("author") or row.get("rights_holder")):
        return "署名许可缺少作者或权利人信息"
    if not row.get("observation_id"):
        return "缺少观察 ID，无法保证同次观察不跨数据划分"
    raw_path = Path(row.get("path", ""))
    if not row.get("path") or raw_path.is_absolute() or raw_path.drive:
        return "来源照片需要项目内相对路径"
    file = (root / raw_path).resolve()
    source_root = (root / "data/crop-identification/sources").resolve()
    if not file.is_relative_to(source_root):
        return "来源照片超出了 crop-identification/sources 目录"
    if not file.is_file():
        return "来源照片文件不存在"
    return ""


def merge_photo(identifier, candidates, previous, targets, review_path, root, accept_source_labels):
    """合并同图元数据；人工决定和备注优先，来源标签接纳明确标为内部实验。"""
    # 优先已有筛选行引用的来源，其次 CN；选择稳定路径避免每次刷新移动引用。
    candidates = sorted(candidates, key=lambda row: (
        row["source"] != previous.get("source"), row["source"] != "gbif-cn", row["source"], row["path"],
    ))
    row = candidates[0]
    reason = next((reason for candidate in candidates
                   if (reason := source_exclusion(candidate, targets, root))), "")
    if not identifier.startswith("inat-photo:") and len({candidate["photo_url"] for candidate in candidates}) > 1:
        reason = "同一媒体 ID 对应不同原图 URL，需复核"
    if len({candidate["label"] for candidate in candidates}) > 1:
        reason = "同一照片在不同来源表的物种标签冲突"
    if len({candidate["observation_id"] for candidate in candidates}) > 1:
        reason = "同一照片的观察 ID 冲突，需复核"

    file = (root / row["path"]).resolve()
    try:
        relative = Path(os.path.relpath(file, review_path.parent.resolve())).as_posix()
    except ValueError:
        # Windows 的其他盘符路径已被来源检查排除，仍保留原值供人工定位。
        relative = row["path"]
    label = previous.get("label") or row["label"]
    decision = (previous.get("decision") or "").strip().lower()
    basis = previous.get("review_basis") or "pending_manual_review"
    if decision not in {"", "keep", "drop"}:
        raise ValueError(f"{identifier} 的 decision 请填 keep、drop 或留空。")
    if label not in targets:
        reason = "人工改标后的类别不在当前目标清单"
    if reason:
        decision, basis = "drop", EXCLUDED_BASIS
    elif decision == "drop":
        basis = "manual_drop" if basis != EXCLUDED_BASIS else basis
    elif decision == "keep":
        if row.get("review", "").strip().lower() == "keep":
            basis = "manual_keep_source_table"
        elif basis != INTERNAL_BASIS or label != previous.get("source_label"):
            basis = "manual_keep"
    elif row.get("review", "").strip().lower() == "keep":
        decision, basis = "keep", "manual_keep_source_table"
    elif accept_source_labels:
        decision, basis = "keep", INTERNAL_BASIS
    else:
        basis = "pending_manual_review"

    # 观察 ID 是跨 CN/ALL 列表的共同身份，不加区域来源前缀，以免拆散同一观察。
    observation = row["observation_id"]
    group = "observation:" + hashlib.sha256(observation.encode()).hexdigest()[:20]
    merged = {field: row.get(field, "") for field in REVIEW_FIELDS}
    merged.update({
        "id": identifier, "decision": decision, "label": label, "path": relative,
        "sha256": previous.get("sha256", ""), "group": group,
        "part": previous.get("part", row.get("organ", "")), "note": previous.get("note", ""),
        "review_basis": basis, "exclusion_reason": reason,
        "source_label": row["label"], "source_review": row.get("review", ""),
        "source_url": row.get("photo_page") or row.get("gbif_occurrence", ""),
        "catalogs": "|".join(sorted({candidate["catalog"] for candidate in candidates})),
        "original_path": row["path"],
        # GBIF 常缺少这两项，合并后仍保留 iNaturalist 的原始标记；casual 不代表专家审核。
        "quality_grade": "|".join(sorted({candidate.get("quality_grade", "") for candidate in candidates} - {""})),
        "captive": "|".join(sorted({str(candidate.get("captive", "")) for candidate in candidates} - {""})),
    })
    return merged


def sync_review(root, *, accept_source_labels=False):
    """更新唯一筛选表，保留旧人工操作；来源消失的照片撤出而不悄悄继续训练。"""
    root = root.resolve()
    targets = load_targets(root)
    review_root = root / "data/crop-identification/review"
    review_path = review_root / "species-review.csv"
    prior_rows = read_rows(review_path, ("id", "decision", "label", "path")) if review_path.exists() else []
    previous = prior_decisions(prior_rows)
    grouped = read_catalogs(review_root)
    rows = [
        merge_photo(identifier, candidates, previous.get(identifier, {}), targets,
                    review_path, root, accept_source_labels)
        for identifier, candidates in grouped.items()
    ]
    rows.extend({
        **old, "decision": "drop", "review_basis": EXCLUDED_BASIS,
        "exclusion_reason": "当前 GBIF/iNaturalist 来源表中已找不到这张照片",
    } for identifier, old in previous.items() if identifier not in grouped)
    rows.sort(key=lambda row: (row["label"], row["id"]))
    # 先写临时 CSV，再替换唯一正式表；失败时不留下半份人工筛选表。
    temporary = review_path.with_suffix(".csv.tmp")
    try:
        write_rows(temporary, REVIEW_FIELDS, rows)
        temporary.replace(review_path)
    finally:
        temporary.unlink(missing_ok=True)
    return review_path, {key: item["name"] for key, item in targets.items()}, rows


def select_photos(review_path, labels, rows, *, accept_source_labels=False):
    """复用通用路径检查；每次实际处理内部来源标签都要显式传实验开关。"""
    selection = read_selection(review_path, labels)
    metadata = {row["path"]: row for row in rows}
    selected = []
    for photo in selection.photos:
        row = metadata[photo.path]
        if row["review_basis"] == INTERNAL_BASIS and not accept_source_labels:
            selection.skipped.append({
                "path": photo.path, "label": photo.label,
                "reason": "此图仅接受了来源标签，需本次显式 --accept-source-labels 或完成人工审核",
            })
            continue
        provenance = json.dumps({field: row.get(field, "") for field in PROVENANCE_FIELDS},
                                ensure_ascii=False, separators=(",", ":"))
        selected.append(replace(photo, note=provenance + ("\n" + photo.note if photo.note else "")))
    selection.photos = selected
    return selection


def prepare_dataset(selection, labels, rows, output, seed=42):
    """先在临时目录完成任务标签和来源表，再原子发布到唯一 prepared 路径。"""
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"工作集已存在：{output}。先核对现有产物，不自动覆盖或新建编号目录。")
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = {row["path"]: row for row in rows}
    with TemporaryDirectory(prefix=".species-prep-", dir=output.parent) as temporary:
        stage = Path(temporary) / "prepared"
        # 复用图像解码、长边缩放、完全重复/近重复合组和观察组划分，不改共享训练代码。
        report = build_dataset(selection, labels, stage, seed, crop="crop_identification")
        label_path = stage / "labels.json"
        actual = json.loads(label_path.read_text(encoding="utf-8"))
        label_path.write_text(
            json.dumps({"task": "crop_identification", "labels": actual["labels"]},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        sources = read_rows(stage / "sources.csv")
        for row in sources:
            origin = metadata[row["source_path"]]
            row.update({field: origin.get(field, "") for field in PROVENANCE_FIELDS})
        write_rows(stage / "sources.csv", (*SOURCE_FIELDS, *PROVENANCE_FIELDS), sources)
        report["task"] = "crop_identification"
        report["review_basis_counts"] = dict(Counter(row["review_basis"] for row in sources))
        report["country_counts"] = dict(Counter(row["country"] or "unknown" for row in sources))
        (stage / "manifest.report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        if output.exists():
            raise FileExistsError(f"发布时发现工作集已存在：{output}")
        stage.rename(output)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="仅同步唯一筛选表并统计，不生成工作图")
    parser.add_argument("--accept-source-labels", action="store_true", help="本次允许来源标签用于内部基线，不代表人工审图")
    parser.add_argument("--prepare", action="store_true", help="生成固定 data/crop-identification/prepared")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    if args.check and args.prepare:
        parser.error("--check 与 --prepare 请选择一个阶段。")
    try:
        review, labels, rows = sync_review(ROOT, accept_source_labels=args.accept_source_labels)
        selection = select_photos(review, labels, rows, accept_source_labels=args.accept_source_labels)
        print_selection(selection, labels, review)
        print("审核依据：", dict(Counter(row["review_basis"] for row in rows)), flush=True)
        print("同次观察与近重复图按组划分；来源标签接纳不代表人工确认物种、器官或画质。", flush=True)
        if args.prepare:
            output = ROOT / "data/crop-identification/prepared"
            report = prepare_dataset(selection, labels, rows, output, args.seed)
            print_report(report, labels, output)
        else:
            print("仅同步筛选表，未复制图片、未做随机增强、未训练。", flush=True)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"物种数据整理未完成：{exc}\n")


if __name__ == "__main__":
    main()
