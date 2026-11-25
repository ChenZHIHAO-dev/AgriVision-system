"""Build the shared manifest schema from prepared image folders."""

import hashlib
from collections import Counter

from PIL import Image

from .groups import group_capture_batches, group_duplicate_photos, separate_label_conflicts
from .images import fingerprint
from .splits import SPLITS, count_groups_by_label, split_capture_groups, split_single_label_groups


# 训练清单的固定列。训练、校准和评估用这些字段找到图片、判定类别与检查数据划分。
MANIFEST_FIELDS = ("path", "label", "group", "sha256", "split")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


# 按类别目录递归收集图片，记录相对路径和图像指纹。无法解码或尺寸太小的文件放进报告。
def scan_images(root, labels):
    rows, invalid = [], []
    for label in labels:
        for path in sorted((root / label).rglob("*")):
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            relative = path.relative_to(root).as_posix()
            try:
                digest, dhash = fingerprint(path)
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                invalid.append({"path": relative, "reason": str(exc)})
                continue
            rows.append({"path": relative, "label": label, "sha256": digest, "dhash": dhash})
    return rows, invalid


# 按独立组数判断单个类别是否足够划出三份数据。组数不足的类别信息留在报告供补充。
def select_ready_labels(clusters, labels):
    available = count_groups_by_label(clusters)
    omitted = {label: available[label] for label in labels if available[label] < len(SPLITS)}
    active = [label for label in labels if label not in omitted]
    if len(active) < 2:
        raise ValueError("至少需要 2 个可分组的类别。每类需要至少 3 个独立组才能覆盖训练、验证和测试。")
    # 从清单中去掉独立组数不足的类别。一个拍摄组含有其他可用类别时，这些照片仍保留在原组内。
    filtered = [
        [row for row in cluster if row["label"] not in omitted]
        for cluster in clusters
    ]
    return [cluster for cluster in filtered if cluster], active, omitted


def manifest_rows(assignments):
    result = []
    # 对组内文件哈希排序后生成稳定组 ID。同一组内字节完全相同的图片只写一条清单记录。
    for cluster, split in assignments:
        digests = "|".join(sorted(row["sha256"] for row in cluster))
        group = hashlib.sha256(digests.encode()).hexdigest()[:20]
        seen = set()
        for row in cluster:
            digest = row["sha256"]
            if digest in seen:
                continue
            seen.add(digest)
            result.append({"path": row["path"], "label": row["label"], "group": group, "sha256": digest, "split": split})
    return result


# 先扫描和查重，再处理标签冲突、合并采集批次，最后划分数据。这一顺序让同源照片留在同一划分。
def build_manifest(root, labels, seed=42, groups=None, *, skip_unready=False):
    rows, invalid = scan_images(root, labels)
    duplicate_clusters = group_duplicate_photos(rows)
    clusters, conflicts = separate_label_conflicts(duplicate_clusters)
    group_count = len(duplicate_clusters)
    # 来源表给出显式采集组时，把这些关系与重复分组一起合并。
    if groups:
        clusters = group_capture_batches(clusters, groups)
        group_count = len(clusters)

    omitted = {}
    if skip_unready:
        clusters, labels, omitted = select_ready_labels(clusters, labels)
        group_count = len(clusters)
    # 按组的来源选择划分办法。没有额外采集组时，重复冲突已排除，剩余的组都是单标签。
    split = split_capture_groups if groups else split_single_label_groups
    records = manifest_rows(split(clusters, labels, seed))
    # 按最终写出的清单统计各标签的图数。比例按组数分配，各组照片数量不同，图数不必精确等比。
    counts = Counter((row["label"], row["split"]) for row in records)
    report = {
        "input_files": len(rows),
        "manifest_images": len(records),
        "invalid": invalid,
        "conflicting_groups": conflicts,
        "groups": group_count,
        "seed": seed,
        "counts": {label: {part: counts[label, part] for part in SPLITS} for label in labels},
    }
    if skip_unready:
        report["labels_with_fewer_than_three_groups"] = omitted
    return records, report
