"""Crop identity has its own result, bundle, and upload lifetime."""

from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest

from app.config import Settings
from app.application import create_app


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path):
    settings = Settings(root=ROOT, runtime=tmp_path / "runtime", models=tmp_path / "models")
    with TestClient(create_app(settings)) as instance:
        yield instance


def photo(size=None):
    if size is None:
        pixels = np.random.default_rng(43).integers(25, 230, (400, 500, 3), dtype=np.uint8)
        image = Image.fromarray(pixels)
    else:
        image = Image.new("RGB", size, "white")
    buffer = BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


def upload(client, content=None):
    return client.post(
        "/api/crop-recognition",
        files={"file": ("crop.jpg", photo() if content is None else content, "image/jpeg")},
    )


def write_crop_bundle(client, **overrides):
    runtime = client.app.state.crop_recognizer
    runtime.bundle.mkdir(parents=True)
    metadata = {
        "task": "crop_identification",
        "architecture": "mobilenet_v3_small",
        "labels": ["rice", "wheat", "unknown"],
        "label_names": {"rice": "水稻", "wheat": "小麦", "unknown": "其他"},
        "version": "unit-crop-version",
        "input_size": 224,
        "threshold": .60,
        "margin": .25,
        "validated": True,
        **overrides,
    }
    runtime.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    runtime.weights.write_bytes(b"test-placeholder-never-loaded")
    return metadata


def test_guest_crop_upload_without_weights_returns_no_guess_or_record(client, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("stand-alone crop recognition must not use disease prediction or chat")

    monkeypatch.setattr(client.app.state.registry, "predict", unexpected)
    monkeypatch.setattr(client.app.state.chat, "answer", unexpected)
    assert client.get("/api/meta").json()["crop_recognition"] == {"ready": False, "version": None, "experimental": False}
    response = upload(client)
    assert response.status_code == 200
    assert response.json() == {
        "status": "model_unavailable",
        "crop_id": None,
        "candidates": [],
        "model_version": None,
        "quality_issues": [],
        "experimental": False,
    }

    store = client.app.state.store
    assert store.temporary == store.image_bytes == {}
    assert not (store.path.parent / "images").exists()
    with store.persistent.connection() as db:
        assert db.execute("SELECT count(*) FROM cases").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 0

    response = client.post(
        "/api/cases",
        headers={"X-Client-ID": "manual-crop-guest"},
        files={"file": ("crop.jpg", photo(), "image/jpeg")},
    )
    assert response.status_code == 422


def test_crop_upload_reuses_validation_and_skips_prediction_for_blurry_photo(client, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("low quality crop photos must not be sent to inference")

    monkeypatch.setattr(client.app.state.crop_recognizer, "predict", unexpected)
    assert upload(client, b"invalid-image").status_code == 422
    assert upload(client, b"x" * (8 * 1024 * 1024 + 1)).status_code == 413

    result = upload(client, photo((64, 64))).json()
    assert result["status"] == "needs_retake"
    assert result["quality_issues"] and result["candidates"] == []


@pytest.mark.parametrize("overrides", [
    {"task": "disease_identification"},
    {"validated": False, "development_ready": True},
    {"development_only": True},
])
def test_wrong_task_and_unreleased_bundles_stay_unavailable(client, overrides):
    write_crop_bundle(client, **overrides)
    assert client.get("/api/meta").json()["crop_recognition"] == {"ready": False, "version": None, "experimental": False}
    assert upload(client).json()["status"] == "model_unavailable"


@pytest.mark.parametrize(("scores", "status", "crop_id"), [
    ([("rice", .95), ("wheat", .03), ("unknown", .02)], "recognized", "rice"),
    ([("rice", .60), ("wheat", .39), ("unknown", .01)], "uncertain", None),
    ([("rice", .58), ("wheat", .21), ("unknown", .21)], "uncertain", None),
    ([("unknown", .97), ("rice", .02), ("wheat", .01)], "uncertain", None),
    (None, "service_error", None),
])
def test_independent_crop_model_supports_more_taxa_than_disease_models(
    client, monkeypatch, scores, status, crop_id
):
    pytest.importorskip("torch")
    pytest.importorskip("torchvision")
    from ml.agrivision_ml import inference

    metadata = write_crop_bundle(client)

    class FakePredictor:
        def __init__(self, bundle, _device):
            assert bundle.name == "crop-identification"
            self.metadata = metadata

        def predict(self, image):
            assert isinstance(image, BytesIO)
            if scores is None:
                raise RuntimeError("synthetic service failure")
            return [{"id": label, "score": score} for label, score in scores]

    monkeypatch.setattr(inference, "Predictor", FakePredictor)
    assert client.get("/api/meta").json()["crop_recognition"] == {
        "ready": True, "version": "unit-crop-version", "experimental": False
    }
    result = upload(client).json()
    assert result["status"] == status
    assert result["crop_id"] == crop_id
    assert result["model_version"] == "unit-crop-version"
    assert result["candidates"] == [
        {"id": label, "name": metadata["label_names"][label], "score": score}
        for label, score in (scores or [])
    ]


@pytest.mark.parametrize(("enabled", "development_only", "ready"), [
    (False, False, False),
    (True, False, True),
    (True, True, False),
])
def test_experimental_crop_bundle_uses_explicit_runtime_switch(
    client, monkeypatch, enabled, development_only, ready
):
    from ml.agrivision_ml import inference

    runtime = client.app.state.crop_recognizer
    runtime.settings = replace(runtime.settings, allow_experimental_models=enabled)
    metadata = write_crop_bundle(
        client, validated=False, development_ready=True, development_only=development_only
    )

    class FakePredictor:
        def __init__(self, bundle, device):
            self.metadata = metadata

        def predict(self, image):
            return [
                {"id": "wheat", "score": .95},
                {"id": "rice", "score": .03},
                {"id": "unknown", "score": .02},
            ]

    monkeypatch.setattr(inference, "Predictor", FakePredictor)
    assert client.get("/api/meta").json()["crop_recognition"] == {
        "ready": ready,
        "version": "unit-crop-version" if ready else None,
        "experimental": ready,
    }
    result = upload(client).json()
    assert result["status"] == ("recognized" if ready else "model_unavailable")
    assert result["experimental"] is ready
    assert result["crop_id"] == ("wheat" if ready else None)
