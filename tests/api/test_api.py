from dataclasses import replace
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest

from app.config import Settings
from app.application import create_app
from app.knowledge import Knowledge

ROOT = Path(__file__).resolve().parents[2]
OWNER = {"X-Client-ID": "test-owner-12345"}
OTHER = {"X-Client-ID": "other-owner-12345"}


@pytest.fixture
def client(tmp_path, admin_hash):
    settings = Settings(
        root=ROOT,
        runtime=tmp_path / "runtime",
        models=tmp_path / "models",
        admin_password_hash=admin_hash,
    )
    with TestClient(create_app(settings)) as instance:
        yield instance


def picture():
    rng = np.random.default_rng(21)
    im = Image.fromarray(rng.integers(25, 220, (400, 500, 3), dtype=np.uint8))
    data = BytesIO()
    im.save(data, "JPEG")
    return data.getvalue()


def test_upload_persists_real_image_without_fabricating_prediction(client):
    result = client.post("/api/cases", headers=OWNER, data={"crop": "wheat"}, files={"file": ("leaf.jpg", picture(), "image/jpeg")})
    assert result.status_code == 201
    case = result.json()
    assert case["status"] == "needs_model" and not case["is_demo"]
    assert case["candidates"] == [] and case["disease_id"] is None
    loaded = client.get("/api/cases/" + case["id"], headers=OWNER).json()
    assert loaded["images"][0]["quality"]["width"] == 500
    image = client.get(case['images'][0]['url'])
    assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg"
    assert client.get("/api/cases/" + case["id"], headers=OTHER).status_code == 404
    assert client.get(f'/api/cases/{case["id"]}/images/{case["images"][0]["id"]}', params={"client_id": OTHER["X-Client-ID"]}).status_code == 404


def test_demo_chat_context_and_deletion_are_bound_to_owner(client, account_headers):
    owner = account_headers(client)
    case = client.post("/api/cases/demo", headers=owner, json={"crop": "maize"}).json()
    assert case["is_demo"] and case["status"] == "demo"
    response = client.post(f'/api/cases/{case["id"]}/messages', headers=owner, json={"text": "还需要补充什么信息？"})
    assert response.status_code == 201
    assert response.json()["provider"] == "knowledge"
    assert "演示" in response.json()["text"]
    loaded = client.get(f'/api/cases/{case["id"]}', headers=owner).json()
    assert len(loaded["messages"]) == 2
    assert client.get("/api/cases", headers=OTHER).json()["items"] == []
    updated = client.post(f'/api/cases/{case["id"]}/context', headers=owner, json={"stage": "拔节期", "note": "田边零星发生"})
    assert updated.json()["stage"] == "拔节期"
    assert client.post(f'/api/cases/{case["id"]}/messages', headers=OTHER, json={"text": "问诊"}).status_code == 401
    assert client.delete(f'/api/cases/{case["id"]}', headers=owner).status_code == 204
    assert client.get(f'/api/cases/{case["id"]}', headers=owner).status_code == 404


def test_conversation_rename_is_saved_for_owner_without_changing_diagnosis(client, account_headers):
    headers = account_headers(client)
    record = client.post("/api/cases/demo", headers=headers, json={"crop": "maize"}).json()
    path = "/api/cases/" + record["id"]
    rename = {"conversation_title": "  秋季玉米叶片观察  "}
    assert client.post(path + "/context", headers=OTHER, json=rename).status_code == 404
    assert client.post(
        path + "/context", headers=headers, json={"conversation_title": "   "}
    ).status_code == 422
    updated = client.post(path + "/context", headers=headers, json=rename).json()
    assert updated["conversation_title"] == "秋季玉米叶片观察"
    assert updated["title"] == record["title"]
    assert client.get(path, headers=headers).json()["conversation_title"] == updated["conversation_title"]
    assert client.get("/api/cases", headers=headers).json()["items"][0]["conversation_title"] == updated["conversation_title"]


def test_invalid_images_and_crop_fail_before_case_creation(client):
    assert client.post("/api/cases", headers=OWNER, data={"crop": "wheat"}, files={"file": ("bad.jpg", b"not an image", "image/jpeg")}).status_code == 422
    assert client.post("/api/cases", headers=OWNER, data={"crop": "rice"}, files={"file": ("leaf.jpg", picture(), "image/jpeg")}).status_code == 422
    assert client.post("/api/cases", headers=OWNER, data={"crop": "wheat"}, files={"file": ("huge.jpg", b"x" * (8 * 1024 * 1024 + 1), "image/jpeg")}).status_code == 413
    assert client.get("/api/cases", headers=OWNER).json()["items"] == []


def test_poor_quality_is_not_sent_to_classifier(client):
    buffer = BytesIO()
    Image.new("RGB", (100, 100), "white").save(buffer, "PNG")
    response = client.post("/api/cases", headers=OWNER, data={"crop": "wheat"}, files={"file": ("small.png", buffer.getvalue(), "image/png")})
    assert response.status_code == 201
    assert response.json()["status"] == "needs_retake"
    assert response.json()["images"][0]["quality"]["issues"]


def test_supplement_preserves_original_image_and_prediction_versions(client):
    case = client.post("/api/cases", headers=OWNER, data={"crop": "peanut"}, files={"file": ("one.jpg", picture(), "image/jpeg")}).json()
    response = client.post(f'/api/cases/{case["id"]}/images', headers=OWNER, files={"file": ("two.jpg", picture(), "image/jpeg")})
    assert len(response.json()["images"]) == 2
    assert len(response.json()["versions"]) == 2
    image_path = client.app.state.store.path.parent / "images" / case["id"]
    assert not image_path.exists()
    assert all(client.get(image['url']).status_code==200 for image in response.json()['images'])
    client.delete(f'/api/cases/{case["id"]}', headers=OWNER)
    assert not image_path.exists()


def test_medication_request_uses_rules_with_no_invented_dosage(client, account_headers):
    owner = account_headers(client)
    case = client.post("/api/cases/demo", headers=owner, json={"crop": "wheat"}).json()
    response = client.post(f'/api/cases/{case["id"]}/messages', headers=owner, json={"text": "给我混配方，每桶兑多少毫升农药？"}).json()
    assert response["provider"] == "rules"
    assert response["products"] == []
    assert "标签" in response["text"]
    assert not any(char.isdigit() for char in response["text"])
    assert client.post(f'/api/cases/{case["id"]}/messages', headers=owner, json={"text": "   "}).status_code == 422


def test_generic_followup_keeps_case_topic_and_photo_question_uses_guide(client, account_headers):
    owner = account_headers(client)
    case = client.post("/api/cases/demo", headers=owner, json={"crop":"wheat"}).json()
    path = f'/api/cases/{case["id"]}/messages'
    generic = client.post(path, headers=owner, json={"text":"还需要补充什么信息？"}).json()
    assert "小麦条锈病" in generic["text"] and "小麦白粉病" not in generic["text"]
    photo = client.post(path, headers=owner, json={"text":"如何拍清楚症状？"}).json()
    assert "怎样拍清作物症状" in photo["text"]
    medication = client.post(path, headers=owner, json={"text":"用药前需要核对什么？"}).json()
    assert medication["provider"] == "rules" and "标签" in medication["text"]


def test_deletion_cannot_race_an_inflight_chat(client, monkeypatch, account_headers):
    owner = account_headers(client)
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    entered, finish = Event(), Event()
    async def delayed(*args, **kwargs):
        entered.set()
        while not finish.is_set():
            await asyncio.sleep(.01)
        return {"text":"测试资料说明","provider":"knowledge","sources":[],"products":[]}
    monkeypatch.setattr(client.app.state.chat, 'answer', delayed)
    case=client.post('/api/cases/demo',headers=owner,json={'crop':'wheat'}).json()
    path='/api/cases/'+case['id']
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(client.post,path+'/messages',headers=owner,json={'text':'补充信息'})
        try:
            assert entered.wait(5)
            assert client.delete(path,headers=owner).status_code==409
        finally:
            finish.set()
        assert future.result(timeout=5).status_code==201
    assert client.delete(path,headers=owner).status_code==204


def test_crop_scoped_retrieval_and_missing_model_metadata(client):
    results = client.get("/api/knowledge", params={"q": "锈病", "crop": "wheat"}).json()["items"]
    assert results and all(row["crop"] in {"wheat", "general"} for row in results)
    assert client.get("/api/knowledge/nonexistent").status_code == 404
    assert not any(m["ready"] for m in client.get("/api/meta").json()["models"])
    assert client.get("/api/cases").status_code == 400


@pytest.mark.anyio
async def test_chat_provider_failure_keeps_local_citations(tmp_path, monkeypatch):
    import httpx
    from app.chat import Chat
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path, deepseek_key="test-key")
    knowledge = Knowledge(ROOT)
    chat = Chat(settings, knowledge)
    async def failed(*args, **kwargs):
        raise httpx.ConnectError("unavailable")
    monkeypatch.setattr(httpx.AsyncClient, "post", failed)
    response = await chat.answer({"crop":"wheat","location":"南阳","stage":"苗期","status":"needs_model","is_demo":False,"title":"待识别","note":"","disease_id":None}, "小麦条锈病需要补拍什么？", [])
    assert response["provider"] == "knowledge" and response["sources"]
    assert "没有可靠的自动识别结论" in response["text"]


@pytest.fixture
def anyio_backend():
    return "asyncio"



def test_explicit_new_crop_does_not_use_or_change_previous_image_context(client, account_headers):
    headers = account_headers(client)
    record = client.post(
        "/api/cases",
        headers=headers,
        data={"crop": "wheat"},
        files={"file": ("leaf.jpg", picture(), "image/jpeg")},
    ).json()
    path = "/api/cases/" + record["id"]
    mismatch = client.post(
        path + "/messages",
        headers=headers,
        json={"text": "黄瓜苗期这张图片是什么病害？"},
    )
    assert mismatch.status_code == 201
    assert mismatch.json()["notice_code"] == "crop_mismatch"
    assert "recognition" not in mismatch.json()

    original_question = client.post(
        path + "/messages",
        headers=headers,
        json={"text": "请结合照片解释病害。"},
    ).json()
    assert original_question["provider"] == "clarification"
    assert original_question["follow_up"]["field"] == "stage"
    assert original_question["recognition"]["image_received"]
    refreshed = client.get(path, headers=headers).json()
    assert refreshed["crop"] == "wheat" and refreshed["stage"] == "不清楚"
