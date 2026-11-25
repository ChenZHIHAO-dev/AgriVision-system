"""Exercise both MobileNetV4 tasks with synthetic images in an in-process API."""

from argparse import Namespace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.agrivision_ml import MOBILENET_V4
from ml.agrivision_ml.calibrate import calibrate
from ml.agrivision_ml.evaluate import evaluate
from ml.agrivision_ml.prepare import prepare
from ml.agrivision_ml.train import parser, read_manifest, train


def train_fixture(work, model_dir, config):
    work.mkdir()
    labels = work / "labels.json"
    labels.write_text(json.dumps(config), encoding="utf-8")
    data = work / "photos"
    for category, label in enumerate(config["labels"]):
        folder = data / label
        folder.mkdir(parents=True)
        for index in range(8):
            rng = np.random.default_rng(category * 100 + index)
            pixels = rng.integers(20, 235, (200, 200, 3), dtype=np.uint8)
            Image.fromarray(pixels).save(folder / f"{index}.png")

    manifest = work / "manifest.csv"
    prepare(data, labels, manifest)
    train(parser().parse_args([
        "--data-root", str(data), "--manifest", str(manifest),
        "--labels", str(labels), "--output", str(model_dir),
        "--architecture", MOBILENET_V4, "--epochs", "1", "--batch-size", "2",
        "--device", "cpu", "--workers", "0", "--no-pretrained",
        "--max-batches", "1", "--development-only",
    ]))
    history = json.loads((model_dir / "training.json").read_text(encoding="utf-8"))
    assert history[0]["optimizer_updates"] == 1
    val_count = sum(row["split"] == "val" for row in read_manifest(manifest))
    assert val_count > 2 and sum(history[0]["counts"]) == val_count
    assert history[0]["loss"] > 0 and history[0]["val_loss"] > 0
    assert 0 <= history[0]["train_accuracy"] <= 1
    with Image.open(model_dir / "training-curves.png") as curves:
        assert curves.format == "PNG"
        curves.verify()
    calibrate(model_dir, data, manifest, "cpu")
    evaluate(Namespace(
        bundle=model_dir, data_root=data, manifest=manifest, device="cpu",
        split="test", activate=False, field_verified=False,
    ))
    metadata = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["development_only"] and not metadata["validated"]
    sample = next(row for row in read_manifest(manifest) if row["split"] == "test")
    return metadata, data / sample["path"]


def check_routes(work, models, fixtures):
    sys.path.insert(0, str(ROOT / "services/api"))
    from fastapi.testclient import TestClient
    from app.config import Settings

    settings = Settings(
        root=ROOT, runtime=work / "runtime", models=models, device="cpu",
        allow_experimental_models=False, serve_web=False,
    )
    with patch.object(Settings, "from_env", return_value=settings):
        from app.application import create_app

    app = create_app(settings)
    crop_metadata, crop_sample = fixtures["crop-identification"]

    def upload(client, url, sample, **form):
        response = client.post(
            url, data=form, files={"file": (sample.name, sample.read_bytes(), "image/png")},
        )
        response.raise_for_status()
        return response.json()

    with TestClient(app, headers={"X-Client-ID": "mobilenetv4-synthetic-preview"}) as client:
        meta = client.get("/api/meta").json()
        assert not meta["crop_recognition"]["ready"]
        assert not any(model["ready"] for model in meta["models"])
        assert upload(client, "/api/crop-recognition", crop_sample)["status"] == "model_unavailable"
        assert upload(client, "/api/cases", crop_sample, crop="wheat")["status"] == "needs_model"

        # Only this in-process test sees the synthetic bundles. Their release flags stay intact.
        with (
            patch.object(app.state.crop_recognizer, "metadata", return_value=crop_metadata),
            patch.object(app.state.registry, "metadata", side_effect=lambda crop: fixtures.get(crop, (None,))[0]),
            patch.object(app.state.chat, "answer", side_effect=AssertionError("Vision must not call chat")),
        ):
            guests_before = set(app.state.store.temporary)
            result = upload(client, "/api/crop-recognition", crop_sample)
            assert result["status"] in {"recognized", "uncertain"}
            assert result["model_version"] == crop_metadata["version"]
            assert {item["id"] for item in result["candidates"]} == set(crop_metadata["labels"])
            assert set(app.state.store.temporary) == guests_before

            for crop in ("wheat", "maize"):
                metadata, sample = fixtures[crop]
                result = upload(client, "/api/cases", sample, crop=crop)
                prediction = result["recognition"]["image_results"][0]
                assert result["crop"] == crop
                assert prediction["status"] in {"identified", "uncertain"}
                assert prediction["model_version"] == metadata["version"]
                assert {item["id"] for item in prediction["candidates"]} == set(metadata["labels"])


def main():
    report_dir = ROOT / ".cache/ml-smoke"
    report_dir.mkdir(parents=True, exist_ok=True)
    recipes = {
        "crop-identification": {
            "task": "crop_identification",
            "labels": {"wheat": "Wheat", "maize": "Maize", "other": "Other"},
        },
        "wheat": {
            "crop": "wheat",
            "labels": {"wheat_stripe_rust": "Stripe rust", "wheat_leaf_rust": "Leaf rust", "healthy": "Healthy"},
        },
        "maize": {
            "crop": "maize",
            "labels": {"maize_southern_rust": "Southern rust", "maize_southern_blight": "Southern blight", "healthy": "Healthy"},
        },
    }
    with TemporaryDirectory(prefix="two-stage-", dir=report_dir) as directory:
        work = Path(directory)
        models = work / "models"
        fixtures = {
            name: train_fixture(work / name, models / name, config)
            for name, config in recipes.items()
        }
        check_routes(work, models, fixtures)
        report = {
            "pipeline": "passed",
            "architecture": MOBILENET_V4,
            "device": "cpu",
            "data": "synthetic",
            "tested_tasks": list(recipes),
            "tested_steps": ["prepare", "train", "calibrate", "evaluate", "api_inference", "release_rejection"],
            "recognition_accuracy": "not_evaluated",
        }
    result = json.dumps(report, indent=2)
    (report_dir / "smoke-report.json").write_text(result + "\n", encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
