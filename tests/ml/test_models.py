import hashlib
import json
from types import SimpleNamespace

import pytest

torch = pytest.importorskip('torch')
from ml.agrivision_ml import calibrate, evaluate
from ml.agrivision_ml.inference import rejection_indices
from ml.agrivision_ml.model import build_model
from ml.agrivision_ml.train import Images, _task_metadata, read_manifest


@pytest.mark.parametrize('architecture', ['efficientnet_b0', 'mobilenet_v3_small', 'convnext_tiny', 'efficientnet_v2_s', 'convnext_small', 'swin_t'])
def test_networks_support_configured_output_classes(architecture):
    torch.set_num_threads(4)
    network=build_model(architecture,4).eval()
    with torch.inference_mode():
        result=network(torch.rand(1,3,96,96))
    assert result.shape==(1,4) and torch.isfinite(result).all()


def test_manifest_refuses_a_group_in_multiple_splits(tmp_path):
    manifest=tmp_path/'bad.csv'
    manifest.write_text('path,label,group,sha256,split\na.png,a,same,a,train\nb.png,a,same,b,test\n')
    with pytest.raises(ValueError, match='multiple splits'):
        read_manifest(manifest)


def test_training_image_path_cannot_escape_root(tmp_path):
    data=Images(tmp_path,[{'path':'../outside.png','label':'a','sha256':'anything'}],['a'],96)
    with pytest.raises(ValueError, match='escapes'):
        data[0]


def test_crop_identification_label_config_has_independent_task():
    crop_config = {
        "task": "crop_identification",
        "labels": {"crop-a": "Crop A", "crop-b": "Crop B", "other": "Other"},
    }
    assert _task_metadata(crop_config) == {"task": "crop_identification"}
    assert _task_metadata({"crop": "wheat"}) == {"crop": "wheat"}
    assert rejection_indices({"labels": ["healthy", "wheat_other"]}) == [1]
    with pytest.raises(ValueError, match="non-reserved crop ID"):
        _task_metadata({
            **crop_config,
            "labels": {"other": "Other", "unknown": "Unknown"},
        })


def test_crop_bundle_calibration_and_evaluation_reject_reserved_predictions(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("synthetic test manifest", encoding="utf-8")
    metadata_file = tmp_path / "metadata.json"
    label_names = {"crop-a": "Crop A", "crop-b": "Crop B", "other": "Other", "unknown": "Unknown"}
    metadata_file.write_text(json.dumps({
        "task": "crop_identification",
        "labels": list(label_names),
        "label_names": label_names,
        "input_size": 64,
        "version": "test-bundle",
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    }), encoding="utf-8")

    # Use deterministic logits for all four classes without training or loading weights.
    classes = torch.arange(len(label_names)).repeat_interleave(20)
    logits = torch.nn.functional.one_hot(classes).float() * 10

    class StaticPredictor:
        def __init__(self, bundle, device):
            self.metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
            self.model = torch.nn.Identity()
            self.device = torch.device(device)

    for module in (calibrate, evaluate):
        monkeypatch.setattr(module, "Predictor", StaticPredictor)
        monkeypatch.setattr(module, "Images", lambda *_, **kwargs: torch.utils.data.TensorDataset(logits, classes))
        monkeypatch.setattr(module, "read_manifest", lambda _: [
            {"split": split} for split in ("val", "test") for _ in classes
        ])

    calibration = calibrate.calibrate(tmp_path, tmp_path, manifest, "cpu")
    assert calibration["accepted_supported"] == 40
    assert calibration["coverage"] == 0.5

    report = evaluate.evaluate(SimpleNamespace(
        bundle=tmp_path, data_root=tmp_path, manifest=manifest, device="cpu",
        split="test", activate=True, field_verified=True,
    ))
    assert report["accuracy"] == 1.0
    assert report["selective"]["accepted"] == 40
    assert report["selective"]["coverage"] == 0.5
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["task"] == "crop_identification"
    assert metadata["validated"] and metadata["field_verified"]


def test_letterbox_training_and_inference_share_geometry():
    # 长方形图补边后仍保留原色区域比例。评估与推理调用同一变换。
    from PIL import Image
    from ml.agrivision_ml.augmentation import preprocessing, MEAN, STD
    photo = Image.new("RGB", (400, 200), (255, 0, 0))
    transform = preprocessing(224, resize="letterbox")
    tensor = transform(photo)
    decoded = tensor * torch.tensor(STD)[:, None, None] + torch.tensor(MEAN)[:, None, None]
    assert tensor.shape == (3, 224, 224)
    assert torch.allclose(decoded[:, 112, 112], torch.tensor([1., 0., 0.]), atol=1e-6)
    assert torch.allclose(decoded[:, 0, 0], torch.tensor([124., 116., 104.])/255)
    for _ in range(30):
        augmented = preprocessing(224, True, resize="letterbox", augmentation="field")(photo)
        assert augmented.shape == tensor.shape and torch.isfinite(augmented).all()
