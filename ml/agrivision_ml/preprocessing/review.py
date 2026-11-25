"""Select approved photos and recover their source groups from the review table."""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .tables import read_rows


# 一条通过初检的照片记录。file 是读取用的绝对路径，path 是筛选表中的相对路径，便于追溯来源。
@dataclass(frozen=True)
class ReviewPhoto:
    file: Path
    path: str
    label: str
    source: str
    sha256: str
    group: str
    note: str
    source_url: str
    license: str
    already_prepared: bool
    part: str = ""


# 保存可处理照片和三类统计信息。初检暂缓的照片与尚未人工决定的照片分别记录。
@dataclass
class Selection:
    photos: list[ReviewPhoto]
    decisions: Counter
    skipped: list[dict]
    pending_by_label: Counter[str]


# 按来源、类别和文件夹逐步缩小处理范围。三个参数同时给出时，照片必须满足所有这些条件。
def filter_review_rows(rows, root, sources, classes, folders):
    if sources:
        available = {row["source"].strip() for row in rows if row["source"]}
        unknown = set(sources) - available
        if unknown:
            raise ValueError(f"筛选表中没有来源：{', '.join(sorted(unknown))}。可用来源：{', '.join(sorted(available))}")
        rows = [row for row in rows if (row["source"] or "").strip() in sources]
    if classes:
        rows = [row for row in rows if (row["label"] or "").strip() in classes]
    # 文件夹筛选按解析后的真实路径判断是否在指定范围内。支持一次指定多个目录。
    if folders:
        roots = [folder.resolve() for folder in folders]
        for folder in roots:
            if not folder.is_dir():
                raise ValueError(f"找不到图片目录：{folder}")
        matches = []
        for row in rows:
            file = (root / (row["path"] or "").strip()).resolve()
            if any(file.is_relative_to(folder) for folder in roots):
                matches.append(row)
        rows = matches
    return rows


def read_selection(review_path, labels, *, sources=(), classes=(), folders=()):
    review_root = review_path.resolve().parent
    baseline_root = review_root.parent / "wheat-v2"
    baseline_images = (baseline_root / "images").resolve()
    baseline_manifest = baseline_root / "manifest.csv"
    # 国内基线清单按相对路径索引。若筛选表引用了国内工作图，可以从这里恢复原采集组和哈希。
    baseline = {}
    if baseline_manifest.is_file():
        baseline = {
            row["path"]: row for row in read_rows(baseline_manifest, ("path", "group", "sha256"))
        }

    photos, skipped = [], []
    decisions = Counter()
    pending_by_label = Counter()
    seen = set()
    # 统计所有筛选决定。只有 keep 行进入后续路径和类别校验，留空的行按候选类别单独计数。
    rows = read_rows(review_path, ("decision", "label", "path", "source", "sha256"))
    for row in filter_review_rows(rows, review_root, sources, classes, folders):
        decision = (row["decision"] or "").strip().lower()
        if decision not in {"", "keep", "drop"}:
            raise ValueError(f"无效筛选决定 {decision!r}，照片：{row['path']}。请填写 keep、drop 或留空。")
        decisions[decision or "pending"] += 1
        if not decision:
            pending_by_label[(row["label"] or "").strip()] += 1
        if decision != "keep":
            continue
        # 已标记保留的行若无法解析，将原因写入初检记录。重复引用同一原图会提示修正筛选表。
        try:
            photo = resolve_photo(row, labels, review_root, baseline_images, baseline)
        except ValueError as exc:
            skipped.append({"path": row["path"], "label": row["label"], "reason": str(exc)})
            continue
        if photo.file in seen:
            raise ValueError(f"筛选表重复标记了同一张照片：{photo.path}")
        seen.add(photo.file)
        photos.append(photo)
    return Selection(photos, decisions, skipped, pending_by_label)


def resolve_photo(row, labels, review_root, baseline_images, baseline):
    # 先按已登记类别校验标签，再解析相对路径，并核对照片是否位于允许的项目数据目录内。
    label = (row["label"] or "").strip()
    if label not in labels:
        raise ValueError("缺少已登记的类别 ID")
    path = Path((row["path"] or "").strip())
    if path.is_absolute() or path.drive:
        raise ValueError("请填写相对筛选表的照片路径")
    file = (review_root / path).resolve()
    in_baseline = file.is_relative_to(baseline_images)
    allowed_roots = (review_root, baseline_images, review_root.parent / "sources")
    if not any(file.is_relative_to(root) for root in allowed_roots):
        raise ValueError("照片路径超出了项目的筛选、基线和原始数据目录")
    if not file.is_file():
        raise ValueError("找不到照片文件")

    sha256 = (row["sha256"] or "").strip().lower()
    group = (row.get("group") or "").strip()
    # 国内工作图沿用既有清单的内容哈希和采集组。后续会直接复用这些 JPEG，而其他来源在整理时编码。
    if in_baseline:
        original = baseline.get(file.relative_to(baseline_images).as_posix())
        if original is None:
            raise ValueError("这张国内照片缺少原清单记录")
        if sha256 and sha256 != original["sha256"]:
            raise ValueError("筛选表的校验值与国内原清单不一致")
        sha256 = original["sha256"]
        group = original["group"]
    source = (row["source"] or "").strip()
    if not source:
        raise ValueError("缺少来源标记")
    # 将来源、许可、备注和拍摄部位一起交给预处理，用于生成逐图来源表。
    return ReviewPhoto(
        file=file, path=path.as_posix(), label=label, source=source, sha256=sha256, group=group,
        note=(row.get("note") or "").strip(), source_url=(row.get("source_url") or "").strip(),
        license=(row.get("license") or "").strip(), already_prepared=in_baseline,
        part=(row.get("part") or "").strip(),
    )
