"""固定来源类别均衡规则和缓存身份，禁止双重重加权。"""
import json

import numpy as np
import pytest

from ml.agrivision_ml import field_weight_probe as module


def make_rows():
    rows = []
    for role, label, count in (("baseline", "a", 8), ("baseline", "b", 2),
                               ("field", "a", 1), ("field", "b", 3)):
        rows.extend({"role": role, "label": label, "split": "train"} for _ in range(count))
    return rows


def test_source_class_totals_equal_without_changing_overall_scale():
    rows = make_rows()
    weights, plan = module.source_class_weights(rows, ["a", "b"])
    for role in ("baseline", "field"):
        for label in ("a", "b"):
            mask = [row["role"] == role and row["label"] == label for row in rows]
            assert weights[mask].sum() == pytest.approx(3.5)
    assert weights.sum() == pytest.approx(len(rows))
    assert plan["class_weight"] is None


def test_validation_labels_never_change_training_weights():
    rows = make_rows()
    before, plan = module.source_class_weights(rows, ["a", "b"])
    rows.extend({"role": "field", "label": "b", "split": "val"} for _ in range(100))
    after, other = module.source_class_weights(rows, ["a", "b"])
    np.testing.assert_array_equal(before, after)
    assert other == plan
    with pytest.raises(ValueError, match="完整类别"):
        module.source_class_weights([row for row in rows if row["label"] != "a"], ["a", "b"])


def cache_fixture(folder):
    rows = [{"path": "a.jpg", "sha256": "image-sha", "label": "a", "split": "train", "role": "baseline"}]
    recipe = {"backbone_sha256": "frozen-backbone", "extra_augmentation_views": 0}
    np.savez_compressed(folder / "features.npz", features=np.array([[1., 2.]], dtype=np.float32))
    sidecar = {"rows": rows, "recipe": recipe, "cache_sha256": module.probe.digest(folder / "features.npz")}
    (folder / "features.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return rows, recipe


def test_cache_rejects_row_identity_or_backbone_changes(tmp_path):
    rows, recipe = cache_fixture(tmp_path)
    assert module.verified_features(tmp_path, rows, recipe).tolist() == [[1., 2.]]
    with pytest.raises(ValueError, match="逐图身份"):
        module.verified_features(tmp_path, [{**rows[0], "sha256": "changed-image"}], recipe)
    with pytest.raises(ValueError, match="配方"):
        module.verified_features(tmp_path, rows, {**recipe, "backbone_sha256": "other"})


def test_cache_rejects_npz_content_tampering(tmp_path):
    rows, recipe = cache_fixture(tmp_path)
    np.savez_compressed(tmp_path / "features.npz", features=np.array([[999., 2.]]))
    with pytest.raises(ValueError, match="NPZ"):
        module.verified_features(tmp_path, rows, recipe)


def test_single_fixed_fit_uses_only_sample_weights(monkeypatch):
    observed = {}
    class Classifier:
        def __init__(self, **kwargs):
            observed.update(kwargs)
        def fit(self, x, y, sample_weight):
            observed["sample_weight"] = sample_weight.copy()
            return self
    monkeypatch.setattr(module, "LogisticRegression", Classifier)
    weights = np.array([.5, 1.5])
    module.fit_fixed_head(np.ones((2, 3)), np.array([0, 1]), weights)
    assert observed["C"] == .1
    assert observed["class_weight"] is None
    np.testing.assert_array_equal(observed["sample_weight"], weights)
