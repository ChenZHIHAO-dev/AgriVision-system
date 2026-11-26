"""EXIF 对照只改变图像朝向；未受影响图的分数必须原样复用。"""
import csv
import hashlib
import json
from types import SimpleNamespace

from PIL import Image
import pytest
import torch
from torchvision.transforms import ToTensor, Resize, Compose

from ml.agrivision_ml import exif_diagnostic as diagnostic


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "weights.pt").write_bytes(b"dummy-model")
    metadata = {"labels": ["a", "b"], "threshold": .6, "margin": .1, "temperature": .8}
    (bundle / "metadata.json").write_text(json.dumps(metadata))
    rows, predictions = [], []
    for i, (label, orientation) in enumerate([("a", 1), ("b", 6), ("a", 0)]):
        path = tmp_path / f"{i}.jpg"
        image = Image.new("RGB", (40, 24), (60, 90, 120))
        exif = image.getexif()
        exif[274] = orientation
        image.save(path, exif=exif)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append({"path": path.name, "label": label, "source": "author", "review": "review"})
        predictions.append({"path": path.name, "true": label, "sha256": digest, "predicted": "a",
                            "correct": label == "a", "confidence": .9, "margin": .8,
                            "accepted": True, "scores": '{"a": 0.9, "b": 0.1}'})
    def write_csv(path, rows):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    manifest = tmp_path / "manifest.csv"
    write_csv(manifest, rows)
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    write_csv(baseline / "predictions.csv", predictions)
    evaluation = {"weights_sha256": diagnostic.digest(bundle / "weights.pt"),
                  "model_metadata_sha256": diagnostic.digest(bundle / "metadata.json"),
                  "external_manifest_sha256": diagnostic.digest(manifest), "labels": ["a", "b"]}
    (baseline / "evaluation.json").write_text(json.dumps(evaluation))
    calls = []
    def model(images):
        calls.append(len(images))
        return torch.tensor([[0., 4.]]).repeat(len(images), 1)
    monkeypatch.setattr(diagnostic, "Predictor", lambda *_: SimpleNamespace(
        model=model, transform=Compose([Resize((16, 16)), ToTensor()])))
    monkeypatch.setattr(diagnostic, "save_confusion", lambda _, __, path: path.write_bytes(b"plot"))
    return tmp_path, bundle, manifest, baseline, rows, calls


def test_only_rotation_images_recomputed_and_all_gates_unchanged(inputs):
    root, bundle, manifest, baseline, rows, calls = inputs
    before = (bundle / "metadata.json").read_bytes()
    result = diagnostic.report(bundle, root, manifest, baseline, root / "corrected", threads=1)
    assert calls == [1]
    assert result["forward_images"] == 1 and result["reused_prediction_images"] == 2
    assert result["before"]["accuracy"] == pytest.approx(2/3)
    assert result["after"]["accuracy"] == 1.
    assert result["wrong_to_correct"] == 1 and result["correct_to_wrong"] == 0
    assert result["fixed_rejection_settings"] == {"threshold": .6, "margin": .1, "temperature": .8}
    corrected = list(csv.DictReader((root / "corrected/predictions.csv").open(encoding="utf-8-sig")))
    assert json.loads(corrected[0]["scores"]) == {"a": .9, "b": .1}
    assert (bundle / "metadata.json").read_bytes() == before


def test_different_weights_cannot_reuse_predictions(inputs):
    root, bundle, manifest, baseline, rows, calls = inputs
    (bundle / "weights.pt").write_bytes(b"another-model")
    with pytest.raises(ValueError, match="身份不同"):
        diagnostic.report(bundle, root, manifest, baseline, root / "bad", threads=1)
    assert calls == []


def test_decoder_applies_orientation_without_editing_original(inputs):
    root, _, _, _, _, _ = inputs
    path = root / "1.jpg"
    before = path.read_bytes()
    row = {"path": path.name, "sha256": hashlib.sha256(before).hexdigest()}
    data = diagnostic.ExifImages(root, [row], lambda image: image.size)
    assert data[0] == (24, 40)
    assert path.read_bytes() == before
