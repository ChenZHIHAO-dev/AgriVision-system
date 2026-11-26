# 小麦人工筛选后的整理入口。输入是筛选 CSV 与标签表，输出是工作图、数据划分和来源统计。
"""Prepare a wheat dataset from reviewed photos and print class and size counts."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from PIL import Image
from tqdm import tqdm

from .images import MIN_SHORT_SIDE, WORK_IMAGE_JPEG_QUALITY, WORK_IMAGE_MAX_SIDE, decode_rgb, write_work_jpeg
from .manifest import MANIFEST_FIELDS, build_manifest
from .review import read_selection
from .splits import SPLITS
from .tables import write_rows


# 来源表的 path 指向生成的工作图，source_path 指向筛选表里的原图。原采集组与最终划分组分列保存。
SOURCE_FIELDS = (
    "path", "label", "width", "height", "split", "group", "source", "source_path",
    "source_sha256", "source_group", "source_url", "license", "note", "part",
)


# 读取小麦类别 ID 与中文名。类别 ID 也会用作输出图片目录名，因此要求统一的命名格式。
def read_label_catalog(path):
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    labels = config.get("labels")
    if config.get("crop") != "wheat" or not isinstance(labels, dict) or len(labels) < 2:
        raise ValueError("标签文件需要包含 crop=wheat 和至少两个类别。")
    for label, name in labels.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", label) or not isinstance(name, str) or not name.strip():
            raise ValueError(f"标签文件中的类别无效：{label!r}")
    return labels


# 读取原始字节并对照已有哈希。解码、方向校正和最小尺寸检查在写工作图之前完成。
def read_photo(photo):
    content = photo.file.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if photo.sha256 and digest != photo.sha256:
        raise ValueError("文件内容与筛选表的 SHA-256 不一致")
    image = decode_rgb(content, review_formats=True)
    if min(image.size) < MIN_SHORT_SIDE:
        raise ValueError(f"图片短边不足 {MIN_SHORT_SIDE} 像素")
    return image, content, digest


# 先把合格的照片整理到临时图像目录。单张无法处理时记下原因，其他照片继续处理。
def stage_photos(photos, images_root):
    rows, rejected = [], []
    for photo in tqdm(photos, desc="Preparing photos", unit="image", disable=None):
        try:
            image, content, digest = read_photo(photo)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            rejected.append({"path": photo.path, "label": photo.label, "reason": str(exc)})
            continue
        # 用筛选表里的原图路径派生工作图文件名，避免不同来源的同名照片相互覆盖。
        photo_id = hashlib.sha256(photo.path.encode("utf-8")).hexdigest()
        relative = f"{photo.label}/{photo_id}.jpg"
        destination = images_root / relative
        # 国内基线 JPEG 已按工作图规格处理，可以复制原字节。其他来源按相同规则重新编码。
        if photo.already_prepared:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(content)
        else:
            write_work_jpeg(image, destination)
        # thumbnail 会改变图像对象的尺寸，所以这里在写入后记录工作图的真实宽高。
        width, height = image.size
        rows.append({
            "path": relative, "label": photo.label, "width": width, "height": height,
            "source": photo.source, "source_path": photo.path, "source_sha256": digest,
            "source_group": photo.group, "source_url": photo.source_url,
            "license": photo.license, "note": photo.note, "part": photo.part,
        })
    return rows, rejected


# 用最终训练清单反查临时工作图。把确定的 split 和 group 合并回来源表，并记录未入选原因。
def retain_manifest_photos(images_root, staged, manifest, report):
    kept = {row["path"]: row for row in manifest}
    conflicts = {path for cluster in report["conflicting_groups"] for path in cluster}
    invalid = {row["path"]: row["reason"] for row in report["invalid"]}
    omitted = report["labels_with_fewer_than_three_groups"]
    sources, discarded = [], []
    for row in staged:
        path = row["path"]
        if path in kept:
            sources.append({**row, "split": kept[path]["split"], "group": kept[path]["group"]})
            continue

        if path in conflicts:
            reason = "疑似重复照片的类别冲突"
        elif path in invalid:
            reason = invalid[path]
        elif row["label"] in omitted:
            reason = "有效独立组少于 3"
        else:
            reason = "文件内容重复"
        discarded.append({"path": row["source_path"], "label": row["label"], "reason": reason})
        # 这里只移除临时区里未进入清单的工作图副本。原始照片路径已经记入排除报告。
        (images_root / path).unlink()

    for folder in images_root.iterdir():
        if folder.name not in report["counts"]:
            folder.rmdir()
    return sources, discarded


# 把如类别、来源这样的成对记录汇总成每类的来源分布。
def class_source_counts(pairs):
    counts = defaultdict(Counter)
    for label, source in pairs:
        counts[label][source] += 1
    return {label: dict(sorted(sources.items())) for label, sources in counts.items()}


# 按实际输出的宽高统计不同分辨率，方便识别过小的样本和各来源的拍摄尺寸差异。
def resolution_counts(sources):
    counts = defaultdict(Counter)
    for row in sources:
        counts[row["label"]][f"{row['width']}x{row['height']}"] += 1
    return {label: dict(sizes.most_common()) for label, sizes in counts.items()}


# 总入口依次整理临时图片、构建带分组的清单、留存选中的图，然后一起发布产物。
def build_dataset(selection, labels, output, seed=42, *, crop="wheat"):
    if not selection.photos:
        raise ValueError("筛选表没有可预处理的 keep 照片。请先确认类别和路径。")
    selected_labels = {photo.label for photo in selection.photos}
    labels = {label: name for label, name in labels.items() if label in selected_labels}
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"输出目录已存在，请使用新的目录名：{output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    # 在同一个父目录下创建临时区。先完成数据和报告，再把整份结果移到正式输出位置。
    with TemporaryDirectory(prefix=".wheat-prep-", dir=output.parent) as staging:
        stage = Path(staging).resolve()
        images_root = stage / "images"
        staged, rejected = stage_photos(selection.photos, images_root)
        # 合并人工标注的原采集组，按组划分后剔除与清单不一致的临时副本。
        groups = {row["path"]: row["source_group"] for row in staged if row["source_group"]}
        print("\n正在查重、合并已知采集组并划分数据……", flush=True)
        manifest, report = build_manifest(images_root, labels, seed, groups, skip_unready=True)
        sources, discarded = retain_manifest_photos(images_root, staged, manifest, report)
        # 生成只含本轮有效类别的 labels.json。报告同时保留待复核、图片失败和组数不足的信息。
        ready_labels = {label: labels[label] for label in report["counts"]}
        report.update({
            "review_decisions": dict(selection.decisions),
            "pending_by_label": dict(selection.pending_by_label),
            "by_source": dict(Counter(row["source"] for row in sources)),
            "by_label_and_source": class_source_counts((row["label"], row["source"]) for row in sources),
            "by_part": dict(Counter(row["part"] for row in sources if row["part"])),
            "resolution_counts": resolution_counts(sources),
            "review_skipped": selection.skipped,
            "image_rejected": rejected,
            "discarded_after_grouping": discarded,
            "work_image": {"format": "JPEG/RGB", "max_long_side": WORK_IMAGE_MAX_SIDE, "quality": WORK_IMAGE_JPEG_QUALITY},
        })

        # manifest.csv 用于训练和评估，sources.csv 用于查原图。模型代码通过本轮标签文件确定输出类别。
        write_rows(stage / "manifest.csv", MANIFEST_FIELDS, manifest)
        write_rows(stage / "sources.csv", SOURCE_FIELDS, sources)
        (stage / "labels.json").write_text(
            json.dumps({"crop": crop, "labels": ready_labels}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (stage / "manifest.report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )

        # 发布前再次确认输出位置和目标目录状态，避免覆盖上一份已有数据。
        if stage.parent != output.parent or output.exists():
            raise FileExistsError(f"无法发布结果到 {output}，目标已存在或目录不匹配")
        stage.rename(output)
    return report


def format_photo_counts(counts):
    return "，".join(f"{source} {count:,} 张" for source, count in counts.items())


# 打印筛选表的初检数量。这里统计的是决策、路径和标签，最终工作图数由后面的报告确定。
def print_selection(selection, labels, review_path):
    decisions = selection.decisions
    print(f"筛选表：{review_path.resolve()}")
    print(f"筛选范围内：keep {decisions['keep']:,}，drop {decisions['drop']:,}，待筛 {decisions['pending']:,}", flush=True)
    print(f"路径和类别初检通过：{len(selection.photos):,} 张，暂缓 {len(selection.skipped):,} 条。", flush=True)
    sources = Counter(photo.source for photo in selection.photos)
    by_label = class_source_counts((photo.label, photo.source) for photo in selection.photos)
    print(f"本次选中 {len(sources)} 个数据集、{len(by_label)} 个有图类别。")
    for source, count in sorted(sources.items()):
        print(f"  {source}: {count:,} 张")
    for label in labels:
        if label in by_label:
            counts = by_label[label]
            print(f"  {labels[label]} ({label}): {sum(counts.values()):,} 张（{format_photo_counts(counts)}）")
    if selection.pending_by_label:
        pending = "，".join(
            f"{labels.get(label, label or '未定类别')} {count:,} 张"
            for label, count in selection.pending_by_label.most_common()
        )
        print(f"  待复核：{pending}")
    for item in selection.skipped[:8]:
        print(f"  待核 {item['path']}　{item['reason']}")


# 显示最终每类的训练、验证、测试图数，附来源和最常见的分辨率。
def print_report(report, labels, output):
    print(f"\n完成：{report['manifest_images']:,} 张，{report['groups']:,} 组。输出：{output.resolve()}")
    print(f"保留 {len(report['by_source'])} 个数据集（{format_photo_counts(report['by_source'])}）。")
    if report["by_part"]:
        print(f"拍摄部位：{format_photo_counts(report['by_part'])}。")
    sizes = report["resolution_counts"]
    for label, counts in report["counts"].items():
        train, val, test = (counts[part] for part in SPLITS)
        common = list(sizes[label].items())[:3]
        dimensions = "，".join(f"{size.replace('x', '×')} {count:,} 张" for size, count in common)
        print(f"  {labels[label]}：{train + val + test:,} 张（训练 {train:,}／验证 {val:,}／测试 {test:,}）")
        print(f"    来源：{format_photo_counts(report['by_label_and_source'][label])}。常见分辨率：{dimensions}")
    # 合并各类别的宽高统计，再按宽高组合去重得到整个数据集的分辨率种数。
    total = Counter()
    for counts in sizes.values():
        total.update(counts)
    print(f"输出分辨率共 {len(total):,} 种，逐图尺寸见 sources.csv。")
    omitted = report["labels_with_fewer_than_three_groups"]
    if omitted:
        names = "、".join(f"{labels[label]}（{count} 组）" for label, count in omitted.items())
        print(f"独立组不足 3 个的已选类别：{names}")
    print("完整计数、分辨率和排除原因见 manifest.report.json。")


def main(argv=None):
    parser = argparse.ArgumentParser(description="从人工筛选表整理小麦数据并打印各类数量与分辨率。")
    parser.add_argument("--review", type=Path, default=Path("data/wheat/review/review.csv"), help="人工筛选表")
    parser.add_argument("--labels", type=Path, default=Path("configs/labels/wheat-review.json"), help="已登记类别")
    parser.add_argument("--output", type=Path, default=Path("data/wheat-mixed"), help="新建的输出目录")
    parser.add_argument("--seed", type=int, default=42, help="划分随机种子")
    parser.add_argument("--source", action="append", default=[], help="筛选表里的来源 ID，可重复指定")
    parser.add_argument("--class", dest="classes", action="append", default=[], help="只选指定类别 ID，可重复指定")
    parser.add_argument("--folder", action="append", default=[], type=Path, help="只选已有清单中位于指定目录下的照片，可重复指定")
    parser.add_argument("--check", action="store_true", help="只统计筛选决定、类别与路径")
    args = parser.parse_args(argv)
    try:
        labels = read_label_catalog(args.labels)
        unknown = set(args.classes) - labels.keys()
        if unknown:
            raise ValueError(f"标签文件中没有类别：{', '.join(sorted(unknown))}")
        if args.classes:
            labels = {label: name for label, name in labels.items() if label in args.classes}
        selection = read_selection(args.review, labels, sources=args.source, classes=args.classes, folders=args.folder)
        display_labels = {label: "健康参考" if label == "healthy" else name for label, name in labels.items()}
        print_selection(selection, display_labels, args.review)
        # 只检查时打印筛选统计。真正整理工作图与数据划分由 build_dataset() 启动。
        if not args.check:
            report = build_dataset(selection, labels, args.output, args.seed)
            print_report(report, display_labels, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"数据预处理未完成：{exc}\n")


if __name__ == "__main__":
    main()
