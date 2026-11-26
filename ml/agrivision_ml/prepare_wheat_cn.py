# 把河南 YOLO 和陕西 LabelMe 两套原始标注整理成按类别存放的整图分类数据。输出包含工作图、采集组、来源和划分清单。
"""Prepare a single-label research dataset from the two domestic wheat archives."""

import argparse
from base64 import b64decode
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from PIL import ImageChops, ImageStat

from .prepare import prepare
from .preprocessing.images import MIN_SHORT_SIDE, decode_rgb, write_work_jpeg
from .preprocessing.tables import read_rows, write_rows


YUANYANG = "henan-yuanyang-15621359"
SHAANXI = "mswdd2022"
# 项目中使用的病害类别 ID 和中文名。下面两张映射表把两个来源的原标签归到这些 ID。
LABELS = {
    "wheat_stripe_rust": "小麦条锈病",
    "wheat_leaf_rust": "小麦叶锈病",
    "wheat_powdery_mildew": "小麦白粉病",
    "wheat_head_blight": "小麦赤霉病",
    "wheat_glume_blotch": "小麦颖枯病",
    "wheat_barley_yellow_dwarf": "小麦黄矮病",
    "healthy": "未发现已支持病害的明显特征",
}
# 元组的下标对应 YOLO 的原始类别号。其中健康叶片和健康麦穗统一归入健康参考。
YOLO_LABELS = (
    "wheat_powdery_mildew", "wheat_head_blight", "wheat_leaf_rust", "wheat_stripe_rust",
    "wheat_glume_blotch", "healthy", "healthy",
)
# LabelMe 先依靠目录映射到病害类，再检查图片内多边形标签是否都在该病害的原始标注集合。
LABELME_LABELS = {
    "Wheat yellow drawf": ("wheat_barley_yellow_dwarf", {"yellow1", "yellow2", "yellow3"}),
    "wheat powdery mildew": ("wheat_powdery_mildew", {"white1", "white2", "white3"}),
    "wheat scab": ("wheat_head_blight", {"cm", "cm1", "cm2", "cm3"}),
    "wheat stripe rust": ("wheat_stripe_rust", {"rust", "rust1"}),
}
OUTPUT_FILES = ("images", "labels.json", "groups.csv", "sources.csv", "manifest.csv", "manifest.report.json")


# 每套数据先读 source.json，核对档案文件位置与声明的字节大小。
def read_source(sources, dataset):
    directory = sources / dataset
    receipt = json.loads((directory / "source.json").read_text(encoding="utf-8"))
    archive = directory / receipt["file"]
    if archive.parent != directory or archive.stat().st_size != receipt["bytes"]:
        raise ValueError(f"Unexpected source archive for {dataset}")
    return archive


# 缺少真实地块编号时，用来源、文件名模式和末尾每 20 个编号估算采集组，供后续整组划分。
def batch_group(source, filename):
    stem = PurePosixPath(filename).stem.casefold()
    match = re.search(r"\d+(?=\D*$)", stem)
    if not match:
        return f"{source}:{stem}"
    number = int(match.group())
    family = stem[:match.start()] + "#" + stem[match.end():]
    return f"{source}:{family}:{number // 20}"


# 读取河南图片和同一原划分下的 YOLO 标注。每行第一项是类别号，框坐标留给原标注。
def yuanyang_items(archive, excluded):
    suffixes = {".jpg", ".jpeg"}
    for member in sorted(archive.namelist()):
        path = PurePosixPath(member)
        if path.suffix.lower() not in suffixes:
            continue
        _, _, split, _ = path.parts
        annotation = f"xiaomai/labels/{split}/{path.stem}.txt"
        ids = {int(line.split()[0]) for line in archive.read(annotation).decode("utf-8").splitlines() if line.strip()}
        if not ids or min(ids) < 0 or max(ids) >= len(YOLO_LABELS):
            raise ValueError(f"Unexpected classes in {annotation}: {ids}")
        # 整图分类要求一张照片对应一个项目类别。允许同类多个框，映射后仍有多类的照片记录为排除。
        classes = {YOLO_LABELS[class_id] for class_id in ids}
        if len(classes) != 1:
            excluded.append({"source": YUANYANG, "original": member, "reason": "multiple_classes"})
            continue
        yield member, annotation, classes.pop(), path.name, split, None


# 从陕西图片子目录读取对应的 LabelMe JSON，并返回标注中内嵌的图片供下游对照。
def shaanxi_items(archive, excluded):
    for member in sorted(archive.namelist()):
        path = PurePosixPath(member)
        if path.suffix.lower() != ".png":
            continue
        prefix, directory, _, _ = path.parts
        label, allowed_shapes = LABELME_LABELS[directory]
        annotation = f"{prefix}/{directory}/json/{path.stem}.json"
        record = json.loads(archive.read(annotation))
        polygons = {shape["label"] for shape in record["shapes"]}
        if not polygons or polygons - allowed_shapes:
            excluded.append({"source": SHAANXI, "original": member, "reason": "unmapped_polygon"})
            continue
        original = PurePosixPath(record["imagePath"].replace("\\", "/")).name
        yield member, annotation, label, original, "", b64decode(record["imageData"])


def export_images(stage, sources, excluded):
    rows = []
    # 两个入口分别解释标注。从这里起共用解码、最小尺寸检查、JPEG 保存和来源记录。
    for dataset, reader in ((YUANYANG, yuanyang_items), (SHAANXI, shaanxi_items)):
        print(f"Reading {dataset}", flush=True)
        with ZipFile(read_source(sources, dataset)) as archive:
            count = len(rows)
            for member, annotation, label, original, split, embedded in reader(archive, excluded):
                image = decode_rgb(archive.read(member))
                if min(image.size) < MIN_SHORT_SIDE:
                    excluded.append({"source": dataset, "original": member, "reason": "image_too_small"})
                    continue
                if embedded:
                    # 公开图片改过文件名，因此同时核对尺寸和缩小后各通道的平均像素差。
                    # 平均像素差允许少量编码误差，用于判断外部文件与标注预览是否仍匹配。
                    preview = decode_rgb(embedded)
                    delta = ImageChops.difference(image.resize((64, 64)), preview.resize((64, 64)))
                    if image.size != preview.size or max(ImageStat.Stat(delta).mean) > 4:
                        excluded.append({"source": dataset, "original": member, "reason": "annotation_image_mismatch"})
                        continue
                # 类别做一级目录，数据来源做二级目录。文件写出后保留原压缩包成员和标注路径，方便回查。
                path = f"{label}/{dataset}/{PurePosixPath(member).stem}.jpg"
                write_work_jpeg(image, stage / "images" / path)

                rows.append({
                    "path": path, "label": label, "source": dataset,
                    "original": member, "annotation": annotation, "original_name": original,
                    "source_split": split, "group": batch_group(dataset, original),
                })
            print(f"Kept {len(rows) - count} single-label photos from {dataset}", flush=True)
    return rows


# 先在临时区生成工作图和清单，再发布这些文件。已有同名输出时中止，保留现有数据。
def build(sources, output, seed):
    sources, output = sources.resolve(), output.resolve()
    if any((output / name).exists() for name in OUTPUT_FILES):
        raise ValueError(f"Choose a fresh output directory to preserve the existing dataset: {output}")

    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".building-", dir=output) as temporary:
        stage = Path(temporary).resolve()
        excluded = []
        rows = export_images(stage, sources, excluded)
        labels = stage / "labels.json"
        labels.write_text(json.dumps({"crop": "wheat", "labels": LABELS}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # 先写入采集组，再让共享清单工具结合图片指纹重新划分。原压缩包的 split 仅供追溯。
        groups = stage / "groups.csv"
        write_rows(groups, ("path", "group"), rows)

        manifest = stage / "manifest.csv"
        print("Checking duplicates and building grouped splits", flush=True)
        report = prepare(stage / "images", labels, manifest, seed=seed, groups_path=groups)
        used = {row["path"]: row for row in read_rows(manifest)}

        # 只将最终进入清单的图片写入来源表。未入选的副本从临时区移除，统计仍能反映导入排除原因。
        kept = []
        by_source = {source: Counter() for source in (YUANYANG, SHAANXI)}
        by_source_label = {source: Counter() for source in by_source}
        for row in rows:
            path = row["path"]
            if path not in used:
                (stage / "images" / path).unlink()
                continue
            split = used[path]["split"]
            kept.append({**row, "split": split})
            by_source[row["source"]][split] += 1
            by_source_label[row["source"]][row["label"]] += 1
        write_rows(stage / "sources.csv", list(kept[0]), kept)
        write_rows(groups, ("path", "group"), kept)
        report.update({
            "status": "research_preprocessing",
            "grouping": "Source and 20 consecutive filename indices; exact and near-duplicate links also grouped. Plot IDs unavailable.",
            "source_archive_split": "Preserved in sources.csv for provenance only. Project manifest uses its own grouped internal split.",
            "by_source_split": by_source, "by_source_label": by_source_label,
            "excluded_during_import": dict(Counter(row["reason"] for row in excluded)),
            "excluded_originals": excluded,
        })
        manifest.with_suffix(".report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        # 产物完成后逐项移到指定目录，同时确认文件来源和目标范围。
        for name in OUTPUT_FILES:
            path = stage / name
            target = output / name
            if not path.resolve().is_relative_to(output) or target.resolve().parent != output:
                raise ValueError(f"Unexpected output path: {path}")
            path.rename(target)

    print(json.dumps({
        "output": str(output), "images": report["manifest_images"],
        "counts": report["counts"], "by_source_split": by_source,
        "excluded_during_import": report["excluded_during_import"],
        "excluded_by_manifest": report["input_files"] - report["manifest_images"],
    }, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=Path("data/wheat/sources/china-wheat"))
    parser.add_argument("--output", type=Path, default=Path("data/wheat/reference"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    build(args.sources, args.output, args.seed)
