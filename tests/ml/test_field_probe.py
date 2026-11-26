"""田间机制对照必须对齐原 clean 缓存，并隔离原最终测试。"""
import csv
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from ml.agrivision_ml import field_probe


def test_reuse_maps_absolute_paths_and_never_uses_augmented_train_views(tmp_path):
    old = tmp_path / "prepared"
    old.mkdir()
    rows = [{"path": "a", "sha256": "sha-a", "label": "a", "split": "train"},
            {"path": "b", "sha256": "sha-b", "label": "b", "split": "val"},
            {"path": "c", "sha256": "sha-c", "label": "a", "split": "test"}]
    targets = [{**row, "path": "prepared/" + row["path"]} for row in reversed(rows)]
    cache = {"train_x": np.array([[10.], [999.], [888.]]), "train_y": np.array([0, 0, 0]),
             "val_x": np.array([[20.]]), "val_y": np.array([1]),
             "test_x": np.array([[30.]]), "test_y": np.array([0])}
    result = field_probe.map_clean_features(cache, rows, targets, old, tmp_path, ["a", "b"])
    assert result[:, 0].tolist() == [30., 20., 10.]
    targets[0]["sha256"] = "changed"
    with pytest.raises(ValueError, match="原图"):
        field_probe.map_clean_features(cache, rows, targets, old, tmp_path, ["a", "b"])


def test_reuse_rejects_exif_changed_pv_before_loading_cache(tmp_path, monkeypatch):
    image = Image.new("RGB", (40, 24))
    exif = image.getexif()
    exif[274] = 6
    image.save(tmp_path / "rotated.jpg", exif=exif)
    monkeypatch.setattr(field_probe.probe, "feature_cache", lambda *_: pytest.fail("must not load mismatched cache"))
    args = SimpleNamespace(data_root=tmp_path)
    with pytest.raises(ValueError, match="方向"):
        field_probe.reuse_pv(args, None, [{"path": "rotated.jpg", "role": "baseline"}], ["a", "b"])


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_original_final_test_never_enters_field_probe(tmp_path):
    rows = []
    for role in ("baseline", "field"):
        for split in ("train", "val"):
            for label in ("a", "b"):
                identifier = f"{role}-{split}-{label}"
                rows.append({"path": identifier, "label": label, "sha256": identifier,
                             "group": identifier, "split": split, "role": role})
    manifest, sources, baseline = (tmp_path / name for name in ("manifest.csv", "sources.csv", "baseline.csv"))
    write(manifest, rows)
    write(sources, rows)
    test = {**rows[0], "path": "original-test", "group": "test-group", "sha256": "heldout-sha", "split": "test"}
    write(baseline, [test])
    assert len(field_probe.read_inputs(manifest, sources, baseline)) == 8
    rows[-1]["sha256"] = "heldout-sha"
    write(manifest, rows)
    with pytest.raises(ValueError, match="最终测试"):
        field_probe.read_inputs(manifest, sources, baseline)


def test_actual_balanced_weights_are_fixed_from_each_training_condition():
    rows = [{"role": role, "split": "train", "label": label} for role, label in
            [("baseline", "a"), ("baseline", "a"), ("baseline", "b"), ("field", "b"), ("field", "b")]]
    rows.append({"role": "field", "split": "val", "label": "a"})
    recipe = field_probe.planned_conditions(rows, ["a", "b"])
    assert recipe["pv_only"]["training_images"] == 3
    assert recipe["pv_only"]["actual_class_weights"] == {"a": .75, "b": 1.5}
    assert recipe["pv_plus_field"]["training_images"] == 5
    assert recipe["pv_plus_field"]["actual_class_weights"] == {"a": 1.25, "b": 5/6}
