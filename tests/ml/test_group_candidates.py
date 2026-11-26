"""候选索引必须覆盖完整的 6 位 Hamming 距离阈值。"""
from ml.agrivision_ml.preprocessing.groups import group_duplicate_photos


def test_near_duplicate_spread_across_all_old_bands_is_not_missed():
    # 6 个变化位分布到旧的四个 16 位段；旧索引没有任何相同段，会漏掉这一对。
    changed = sum(1 << bit for bit in (0, 1, 16, 17, 32, 48))
    rows = [dict(path="a", sha256="a", dhash=0), dict(path="b", sha256="b", dhash=changed)]
    assert len(group_duplicate_photos(rows)) == 1


def test_shared_band_alone_does_not_merge_distant_images():
    rows = [dict(path="a", sha256="a", dhash=0), dict(path="b", sha256="b", dhash=(1 << 8)-1)]
    assert len(group_duplicate_photos(rows)) == 2
