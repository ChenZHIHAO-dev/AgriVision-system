"""线性头导出必须保持 sklearn 与部署网络的分类概率一致。"""
import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
import torch
from ml.agrivision_ml.linear_probe import linear_weights, prediction_metrics


@pytest.mark.parametrize('classes', [2, 4])
def test_exported_head_preserves_class_probabilities(classes):
    rng = np.random.default_rng(42)
    x = rng.normal(size=(100, 8)).astype('float32')
    y = np.arange(100) % classes
    model = LogisticRegression(max_iter=500).fit(x, y)
    weights, bias = linear_weights(model)
    logits = torch.from_numpy(x) @ torch.from_numpy(weights).T + torch.from_numpy(bias)
    np.testing.assert_allclose(logits.softmax(1).numpy(), model.predict_proba(x), rtol=1e-5, atol=1e-6)


def test_metrics_include_missed_classes():
    report = prediction_metrics(np.array([0, 1, 2]), np.array([0, 1, 1]), 3)
    assert report['accuracy'] == 2 / 3
    assert report['recall'][2] == 0


@pytest.fixture
def probe_inputs(tmp_path):
    """只构造几张本地小图；编码器在测试内替换，不下载骨干权重。"""
    import csv
    import hashlib
    import json
    from types import SimpleNamespace
    from PIL import Image

    root = tmp_path / "images"
    root.mkdir()
    rows = []
    for split in ("train", "val", "test"):
        for index, label in enumerate(("a", "b")):
            path = root / f"{split}-{label}.png"
            Image.new("RGB", (16, 16), (index * 80, len(rows) * 20, 0)).save(path)
            rows.append({
                "path": path.name, "label": label, "split": split,
                "group": f"{split}-{label}",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"task": "crop_identification", "labels": {"a": "A", "b": "B"}}))
    output = tmp_path / "probe"
    output.mkdir()
    args = SimpleNamespace(
        data_root=root, manifest=manifest, labels=labels, output=output,
        architecture="convnext_tiny", input_size=224, views=2,
        augmentation="light", seed=42, batch_size=2, threads=1,
    )
    model = torch.nn.Linear(3, 2).eval().requires_grad_(False)
    return args, model, rows, ["a", "b"]


def cache_with_fake_encoder(probe_inputs, monkeypatch):
    from ml.agrivision_ml import linear_probe
    calls = []

    def encode(model, root, rows, labels, size, *, training=False, **kwargs):
        calls.append((training, {row["split"] for row in rows}))
        targets = np.array([labels.index(row["label"]) for row in rows])
        return np.eye(len(labels), dtype=np.float32)[targets], targets

    monkeypatch.setattr(linear_probe, "encode", encode)
    cached = linear_probe.feature_cache(*probe_inputs)
    return cached, calls


def test_only_training_features_receive_augmentation_and_cache_is_reused(probe_inputs, monkeypatch):
    from ml.agrivision_ml import linear_probe
    cached, calls = cache_with_fake_encoder(probe_inputs, monkeypatch)
    assert cached["train_x"].shape == (6, 2)
    assert cached["val_x"].shape == cached["test_x"].shape == (2, 2)
    assert [split for training, split in calls if training] == [{"train"}, {"train"}]
    assert sum(not training for training, _ in calls) == 3
    again = linear_probe.feature_cache(*probe_inputs)
    assert len(calls) == 5
    for name, value in cached.items():
        np.testing.assert_array_equal(value, again[name])
    assert not list(probe_inputs[0].output.glob("*.tmp"))
    assert not list(probe_inputs[0].output.glob(".features.pending*"))


def test_cached_features_do_not_hide_changed_original_image(probe_inputs, monkeypatch):
    from ml.agrivision_ml import linear_probe
    cache_with_fake_encoder(probe_inputs, monkeypatch)
    args, _, rows, _ = probe_inputs
    path = args.data_root / rows[0]["path"]
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="清单不一致"):
        linear_probe.feature_cache(*probe_inputs)


def test_cached_features_require_same_actual_backbone(probe_inputs, monkeypatch):
    from ml.agrivision_ml import linear_probe
    cache_with_fake_encoder(probe_inputs, monkeypatch)
    with torch.no_grad():
        probe_inputs[1].weight.add_(0.1)
    with pytest.raises(ValueError, match="冻结骨干"):
        linear_probe.feature_cache(*probe_inputs)


def test_cache_binds_images_implementation_and_checks_saved_bytes(probe_inputs, monkeypatch):
    from ml.agrivision_ml import linear_probe
    cache_with_fake_encoder(probe_inputs, monkeypatch)
    original = linear_probe.digest
    with monkeypatch.context() as patch:
        patch.setattr(linear_probe, "digest", lambda path: "changed-images-code" if path.name == "train.py" else original(path))
        with pytest.raises(ValueError, match="实验配置"):
            linear_probe.feature_cache(*probe_inputs)
    cache = probe_inputs[0].output / "features.npz"
    cache.write_bytes(cache.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="缓存内容校验"):
        linear_probe.feature_cache(*probe_inputs)


def test_partition_leakage_is_rejected_before_loading_backbone(probe_inputs, monkeypatch):
    import csv
    from ml.agrivision_ml import linear_probe
    args, _, rows, _ = probe_inputs
    rows[2]["group"] = rows[0]["group"]
    with args.manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    def forbidden(*args, **kwargs):
        pytest.fail("invalid splits must be rejected before model construction")
    monkeypatch.setattr(linear_probe, "build_model", forbidden)
    with pytest.raises(ValueError, match="multiple splits"):
        linear_probe.run(args)


def test_image_path_cannot_escape_manifest_root(probe_inputs):
    from ml.agrivision_ml import linear_probe
    args, _, rows, _ = probe_inputs
    escaped = [{**rows[0], "path": "../labels.json"}]
    with pytest.raises(ValueError, match="图片路径"):
        linear_probe.validate_source_images(args.data_root, escaped)
