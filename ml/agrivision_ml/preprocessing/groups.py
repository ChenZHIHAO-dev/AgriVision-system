"""Group duplicate photos and capture batches before splitting."""

from collections import defaultdict


# 用并查集维护照片之间的连通关系。照片 A 与 B 同组、B 与 C 同组时，三张照片都会进入一个分组。
class _DisjointSets:
    def __init__(self, size):
        self.parents = list(range(size))

    def find(self, index):
        # 沿父指针找代表节点，同时缩短查询路径。之后再查询同组照片时可以更快找到代表。
        while self.parents[index] != index:
            self.parents[index] = self.parents[self.parents[index]]
            index = self.parents[index]
        return index

    def union(self, first, second):
        self.parents[self.find(first)] = self.find(second)


# 先根据文件内容合并完全重复的照片，再根据感知哈希合并近重复候选。
def group_duplicate_photos(rows):
    sets = _DisjointSets(len(rows))
    exact = {}
    buckets = defaultdict(list)
    for index, row in enumerate(rows):
        digest = row["sha256"]
        sets.union(index, exact.setdefault(digest, index))
        dhash = row["dhash"]
        candidates = set()
        # 阈值是 6 位，因此拆成 7 段（10 + 6×9 = 64）。距离不超过 6 的两图
        # 至少有一段相同，才能保证候选不漏。旧的 4 段会漏掉差异分散在四段的近重复。
        offset = 0
        for band, width in enumerate((10, 9, 9, 9, 9, 9, 9)):
            key = (band, (dhash >> offset) & ((1 << width) - 1))
            candidates.update(buckets[key])
            buckets[key].append(index)
            offset += width
        # 异或后的 1 的位数就是两个 dHash 不同的位数。相差最多 6 位的候选合并。
        for other in candidates:
            if (rows[other]["dhash"] ^ dhash).bit_count() <= 6:
                sets.union(index, other)

    # 根据并查集的代表编号收集各照片组。后续划分将这些照片一起安排。
    clusters = defaultdict(list)
    for index, row in enumerate(rows):
        clusters[sets.find(index)].append(row)
    return list(clusters.values())


# 同一重复组出现多个标签时暂缓整个组。保留路径记录，便于回头核查人工标注。
def separate_label_conflicts(clusters):
    clean, conflicts = [], []
    for cluster in clusters:
        labels = {row["label"] for row in cluster}
        if len(labels) > 1:
            conflicts.append([row["path"] for row in cluster])
        else:
            clean.append(cluster)
    return clean, conflicts


# 将来源表标了同一采集组的照片继续合并。这一步允许一个采集组含多个类别，划分时会整体移动。
def group_capture_batches(clusters, groups):
    sets = _DisjointSets(len(clusters))
    named = {}
    for index, cluster in enumerate(clusters):
        for row in cluster:
            if group := groups.get(row["path"]):
                sets.union(index, named.setdefault(group, index))

    connected = defaultdict(list)
    for index, cluster in enumerate(clusters):
        connected[sets.find(index)].extend(cluster)
    return list(connected.values())
