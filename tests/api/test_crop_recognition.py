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
def client(tmp_path, admin_hash, account_headers):
    settings = Settings(root=ROOT, runtime=tmp_path / "runtime", models=tmp_path / "models", admin_password_hash=admin_hash)
    with TestClient(create_app(settings)) as instance:
        instance.headers.update(account_headers(instance))
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


def test_authenticated_crop_upload_without_weights_returns_no_guess_or_record(client, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("stand-alone crop recognition must not use disease prediction or chat")

    monkeypatch.setattr(client.app.state.registry, "predict", unexpected)
    monkeypatch.setattr(client.app.state.chat, "answer", unexpected)
    assert client.get("/api/meta").json()["crop_recognition"] == {"ready": False, "version": None, "experimental": False, "labels": [], "label_names": {}}
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
    assert client.get("/api/meta").json()["crop_recognition"] == {"ready": False, "version": None, "experimental": False, "labels": [], "label_names": {}}
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
        "ready": True, "version": "unit-crop-version", "experimental": False,
        "labels": metadata["labels"], "label_names": metadata["label_names"],
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
        "labels": metadata["labels"] if ready else [],
        "label_names": metadata["label_names"] if ready else {},
    }
    result = upload(client).json()
    assert result["status"] == ("recognized" if ready else "model_unavailable")
    assert result["experimental"] is ready
    assert result["crop_id"] == ("wheat" if ready else None)


def test_real_uploaded_bytes_load_model_and_return_crop_candidates(client, tmp_path):
    """真实 HTTP→BytesIO→Predictor→网络，防止只 mock 时漏掉上传输入类型错误。"""
    torch = pytest.importorskip("torch")
    from ml.agrivision_ml.inference import Predictor
    from ml.agrivision_ml.model import build_model

    previous_threads = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        runtime = client.app.state.crop_recognizer
        runtime.settings = replace(runtime.settings, device="cpu", allow_experimental_models=True)
        write_crop_bundle(client, input_size=64, resize="letterbox", temperature=1.,
                          validated=False, development_ready=True, development_only=False,
                          release_stage="admin_internal_preview")
        # 小型真实网络的确定性分类头，避免下载权重或依赖随机分类碰巧成功。
        model = build_model("mobilenet_v3_small", 3, input_size=64)
        with torch.no_grad():
            model.classifier[-1].weight.zero_()
            model.classifier[-1].bias.copy_(torch.tensor([4., 0., -4.]))
        torch.save(model.state_dict(), runtime.weights)
        content = photo()
        path = tmp_path / "crop.jpg"
        path.write_bytes(content)
        predictor = Predictor(runtime.bundle, "cpu")
        direct = predictor.predict(path)
        stream = BytesIO(content)
        stream.seek(5)
        assert predictor.predict(stream) == direct and stream.tell() == 5

        response = upload(client, content)
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "recognized"
        assert result["crop_id"] == "rice"
        assert result["experimental"] is True
        assert result["model_version"] == "unit-crop-version"
        assert result["candidates"] == direct
        assert isinstance(runtime._cache[1], Predictor)
    finally:
        torch.set_num_threads(previous_threads)


@pytest.mark.parametrize(("crop", "name", "alias", "stage"), [
    ("cucumber", "黄瓜", "胡瓜", "伸蔓期"),
    ("tomato", "番茄", "西红柿", "结果期"),
])
def test_new_crop_without_bundle_keeps_real_availability_and_context(client, crop, name, alias, stage):
    from app.context import fill_explicit_context
    from app.crops import CROP_NAMES, STAGES
    from app.schemas import ConsultationRequest

    meta = client.get("/api/meta").json()
    states = {item["crop"]: item for item in meta["models"]}
    assert list(states) == list(CROP_NAMES)
    assert states[crop]["ready"] is False and states[crop]["version"] is None
    assert states[crop]["labels"] == [] and states[crop]["label_names"] == {}
    assert stage in meta["stages"][crop] == STAGES[crop]
    assert ConsultationRequest.model_json_schema()["properties"]["crop"]["anyOf"][0]["enum"] == list(CROP_NAMES)
    context = {"crop": None, "stage": "不清楚", "images": []}
    fill_explicit_context(context, alias + stage + "叶子发黄")
    assert context["crop"] == crop and context["crop_name"] == name and context["stage"] == stage

    record = client.post("/api/cases", data={"crop": crop, "stage": stage},
                         files={"file": ("leaf.jpg", photo(), "image/jpeg")})
    assert record.status_code == 201
    saved = record.json()
    assert saved["crop"] == crop and saved["crop_name"] == name and saved["stage"] == stage
    assert saved["status"] == "needs_model" and saved["disease_id"] is None
    assert saved["candidates"] == [] and saved["model_version"] is None
    assert saved["advice"]["sources"] == []
    demo = client.post("/api/cases/demo", json={"crop": crop}).json()
    assert name in demo["title"] and demo["is_demo"]
    assert demo["disease_id"] is None and demo["candidates"] == []
    assert demo["advice"]["sources"] == [] and demo["advice"]["products"] == []
    assert client.post("/api/consultations", json={"crop": crop, "stage": stage}).status_code == 201
    assert client.post("/api/consultations", json={"crop": "rice"}).status_code == 422
    assert client.post("/api/consultations", json={}).status_code == 201
    assert client.post("/api/consultations", json={"crop": crop, "stage": "x" * 41}).status_code == 422


@pytest.mark.parametrize(("crop", "name"), [("cucumber", "黄瓜"), ("tomato", "番茄")])
def test_species_confirmation_routes_to_its_own_new_disease_bundle(client, monkeypatch, crop, name):
    from ml.agrivision_ml import inference

    identity = write_crop_bundle(client, labels=[crop, "rice"], label_names={crop: name, "rice": "水稻"})
    folder = client.app.state.registry.settings.models / crop
    folder.mkdir()
    disease = crop + "_leaf_spot"
    disease_meta = {**identity, "task": "disease_identification", "crop": crop,
                    "labels": [disease, "healthy"], "label_names": {disease: "测试叶斑标签", "healthy": "健康参考"},
                    "version": "test-" + crop, "validated": False, "development_ready": True}
    (folder / "metadata.json").write_text(json.dumps(disease_meta), encoding="utf-8")
    (folder / "weights.pt").write_bytes(b"test-placeholder-never-loaded")
    registry = client.app.state.registry
    registry.settings = replace(registry.settings, allow_experimental_models=True)
    invoked = []

    class FakePredictor:
        def __init__(self, bundle, _device):
            self.crop = bundle.name
            self.metadata = identity if self.crop == "crop-identification" else disease_meta
        def predict(self, image):
            # 独立物种识别使用内存；病害服务复用已保存且有归属的工作图。
            if self.crop == "crop-identification":
                assert isinstance(image, BytesIO)
            else:
                assert isinstance(image, Path) and image.is_file()
            invoked.append(self.crop)
            labels = self.metadata["labels"]
            return [{"id": key, "name": self.metadata["label_names"][key], "score": score}
                    for key, score in zip(labels, [.98, .02])]

    monkeypatch.setattr(inference, "Predictor", FakePredictor)
    candidates = upload(client).json()
    assert candidates["crop_id"] == crop
    state = next(item for item in client.get("/api/meta").json()["models"] if item["crop"] == crop)
    assert state["ready"] and state["experimental"] and state["version"] == "test-" + crop
    assert state["labels"] == [disease, "healthy"] and state["label_names"] == disease_meta["label_names"]
    response = client.post("/api/cases", data={"crop": candidates["crop_id"]},
                           files={"file": ("leaf.jpg", photo(), "image/jpeg")})
    assert response.status_code == 201
    saved = response.json()
    assert saved["crop"] == crop and saved["disease_id"] == disease
    assert saved["model_version"] == "test-" + crop and saved["experimental"]
    assert saved["advice"]["sources"] == []  # 新病名无资料卡时不冒用其他作物。
    retry = client.post("/api/cases/" + saved["id"] + "/retry")
    assert retry.status_code == 200 and retry.json()["crop"] == crop
    assert invoked == ["crop-identification", crop, crop]
    changed = client.post("/api/cases/" + saved["id"] + "/context", json={"crop": "wheat"})
    assert changed.status_code == 409
