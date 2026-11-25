"""Deterministic train, validation and test assignments for whole groups."""

import random
from collections import Counter, defaultdict


SPLITS = ("train", "val", "test")


# 每个分组对组内每个类别只计数一次。多张相近照片不会被当作多个独立组。
def count_groups_by_label(clusters):
    return Counter(label for cluster in clusters for label in {row["label"] for row in cluster})


# 计算某一类别为验证集和测试集分别留出的组数，目标各约 15%，至少各留 1 组。
def holdout_count(count, label):
    if count < len(SPLITS):
        raise ValueError(f"{label}: at least three independent groups are required; got {count}")
    return max(1, round(count * .15))


# 组内只有一种标签时按类别独立划分。固定种子打乱分组，把组整体分给验证、测试或训练。
def split_single_label_groups(clusters, labels, seed):
    by_label = defaultdict(list)
    for cluster in clusters:
        by_label[cluster[0]["label"]].append(cluster)
    for label in labels:
        groups = by_label[label]
        held_out = holdout_count(len(groups), label)
        random.Random(seed).shuffle(groups)
        for index, cluster in enumerate(groups):
            split = "val" if index < held_out else "test" if index < held_out * 2 else "train"
            yield cluster, split


# 支持同一拍摄批次含多个标签的划分。整组进入一个集合，并尽量使每个标签接近按组数计算的目标。
def split_capture_groups(clusters, labels, seed):
    groups = [(cluster, sorted({row["label"] for row in cluster})) for cluster in clusters]
    available = count_groups_by_label(clusters)
    targets = {}
    for label in labels:
        count = available[label]
        held_out = holdout_count(count, label)
        targets[label] = {"train": count - 2 * held_out, "val": held_out, "test": held_out}

    # 优先安排有效组较少的类别。先按固定种子打乱，同等稀缺度的组保留打乱后的顺序。
    random.Random(seed).shuffle(groups)
    groups.sort(key=lambda item: min(available[label] for label in item[1]))
    # remaining 记录还没处理的组数，missing 记录仍缺少该类别的划分，counts 记录已分到各集合的组数。
    remaining = available.copy()
    missing = {label: set(SPLITS) for label in labels}
    counts = {split: Counter() for split in SPLITS}
    for cluster, group_labels in groups:
        remaining.subtract(group_labels)
        # 候选划分要给剩余组留足空间，让相关类别仍能覆盖训练、验证和测试。
        feasible = [
            split for split in SPLITS
            if all(len(missing[label]) - (split in missing[label]) <= remaining[label] for label in group_labels)
        ]
        if not feasible:
            raise ValueError(
                "Could not assign the connected groups with all labels in train, val and test. "
                "Check the capture groups or choose another seed."
            )
        # 优先补足还缺类别的划分。若有多个可选，再比较该划分离目标组数还有多远。
        split = max(
            feasible,
            key=lambda candidate: (
                sum(candidate in missing[label] for label in group_labels),
                sum(1 - counts[candidate][label] / targets[label][candidate] for label in group_labels),
            ),
        )
        # 确定归属后更新统计，再将同组所有照片和同一个划分一并交给清单生成。
        counts[split].update(group_labels)
        for label in group_labels:
            missing[label].discard(split)
        yield cluster, split
