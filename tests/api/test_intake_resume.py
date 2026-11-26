"""回答优先、资料可跳过；旧版本待答问题仍可由用户主动接续。"""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient

from app.application import create_app
from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
OWNER = {"X-Client-ID": "intake-test-owner"}


@pytest.fixture
def app_client(tmp_path, monkeypatch, account_headers, admin_hash):
    app = create_app(Settings(
        root=ROOT, runtime=tmp_path, models=tmp_path / "models",
        admin_password_hash=admin_hash, deepseek_key="test-only-answer-first",
    ))
    generated = []

    async def respond(_self, url, **kwargs):
        payload = kwargs["json"]
        generated.append({
            "text": payload["messages"][-1]["content"],
            "context": json.loads(payload["messages"][0]["content"].rsplit("\n", 1)[-1]),
            "payload": payload,
        })
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "可以先核对适用条件，再按实际情况安排。"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", respond)
    with TestClient(app) as client:
        client.headers.update(account_headers(client))
        yield client, generated


def new_case(client, **fields):
    case = client.post("/api/consultations", headers=OWNER, json=fields).json()
    return "/api/cases/" + case["id"]


def seed_legacy_pending(client, path):
    """只模拟升级前已存在的待答记录，新消息不再创建这种状态。"""
    store = client.app.state.store
    case_id = path.rsplit("/", 1)[-1]
    owner = store.owner_of(case_id)
    case = store.get(owner, case_id)
    case["pending_question"] = {
        "id": "legacy-question", "text": "叶片有黄斑，如何观察？",
        "model": "deepseek-flash", "thinking": False, "web_search": False,
        "attachment_ids": [], "image_ids": [],
    }
    store.save(owner, case)
    return "legacy-question"


@pytest.mark.parametrize("question", [
    "什么是小麦条锈病？", "玉米大喇叭口期怎么管理？",
    "水稻种植如何安排施肥？", "番茄种植需要注意哪些事项？",
    "如何预防小麦白粉病？",
])
def test_agricultural_questions_answer_immediately_without_forms(app_client, question):
    client, generated = app_client
    path = new_case(client)
    response = client.post(path + "/messages", json={"text": question})
    answer = response.json()
    assert response.status_code == 201 and answer["provider"] == "deepseek"
    assert generated[0]["text"] == question
    assert "follow_up" not in answer and "pending_question_id" not in answer
    assert "context_suggestion" not in answer and "photo_suggestion" not in answer
    assert "pending_question" not in client.get(path).json()
    assert generated[0]["context"]["response_policy"]["answer_first"] is True


def test_field_symptoms_answer_before_optional_context_and_photo(app_client):
    client, generated = app_client
    path = new_case(client)
    answer = client.post(path + "/messages", json={"text": "叶片出现黄斑，应该怎么观察？"}).json()
    assert answer["provider"] == "deepseek" and len(generated) == 1
    assert answer["context_suggestion"]["field"] == "crop"
    assert answer["context_suggestion"]["optional"] is True
    assert answer["photo_suggestion"]["optional"] is True
    assert "pending_question" not in client.get(path).json()


def test_skipped_fields_persist_and_context_update_never_calls_model(app_client):
    client, generated = app_client
    path = new_case(client)
    client.post(path + "/messages", json={"text": "叶片有白斑，怎么观察？"})
    updated = client.post(path + "/context", json={"skip_context_fields": ["crop", "stage", "location"]})
    assert updated.status_code == 200
    assert set(updated.json()["skipped_context_fields"]) == {"crop", "stage", "location"}
    assert len(generated) == 1
    client.get(path)
    answer = client.post(path + "/messages", json={"text": "叶片还是发黄，接下来怎么观察？"}).json()
    assert answer["provider"] == "deepseek" and len(generated) == 2
    assert "context_suggestion" not in answer and "photo_suggestion" not in answer
    assert set(generated[-1]["context"]["response_policy"]["skipped_context_fields"]) == {"crop", "stage", "location"}
    updated = client.post(path + "/context", json={"crop": "wheat", "stage": "苗期"}).json()
    assert updated["skipped_context_fields"] == ["location"]
    assert len(generated) == 2


@pytest.mark.parametrize("alias,crop", [
    ("麦子", "wheat"), ("苞谷", "maize"), ("包谷", "maize"), ("落花生", "peanut"),
])
def test_typed_context_saves_without_reanswering_or_charging(app_client, alias, crop):
    client, generated = app_client
    path = new_case(client)
    client.post(path + "/messages", json={"text": "叶片有斑点，如何观察？"})
    response = client.post(path + "/messages", json={"text": "种的是" + alias})
    assert response.status_code == 201 and response.json()["provider"] == "rules"
    response = client.post(path + "/messages", json={"text": "现在是苗期"})
    assert response.json()["provider"] == "rules" and len(generated) == 1
    case = client.get(path).json()
    assert case["crop"] == crop and case["stage"] == "苗期"
    answer = client.post(path + "/messages", json={"text": "叶片上有白斑，如何观察？"}).json()
    assert len(generated) == 2 and answer["provider"] == "deepseek"
    assert answer.get("context_suggestion", {}).get("field") not in {"crop", "stage"}


@pytest.mark.parametrize("skip,decline", [("先跳过", "没有照片"), ("我现在不知道", "我没有照片")])
def test_typed_skip_and_photo_decline_are_respected(app_client, skip, decline):
    client, generated = app_client
    path = new_case(client)
    client.post(path + "/messages", json={"text": "叶片出现黄斑，怎么处理？"})
    skipped = client.post(path + "/messages", json={"text": skip}).json()
    assert skipped["provider"] == "rules"
    declined = client.post(path + "/messages", json={"text": decline}).json()
    assert declined["provider"] == "rules" and len(generated) == 1
    answer = client.post(path + "/messages", json={"text": "叶片仍然发黄，怎么观察？"}).json()
    assert answer["provider"] == "deepseek"
    assert answer.get("context_suggestion", {}).get("field") != "crop"
    assert "photo_suggestion" not in answer


def test_known_crop_is_not_repeated_and_each_optional_field_is_suggested_once(app_client):
    client, _ = app_client
    path = new_case(client, crop="wheat")
    results = [
        client.post(path + "/messages", json={"text": "小麦叶片有黄斑，应该怎么观察？"}).json()
        for _ in range(3)
    ]
    assert [r.get("context_suggestion", {}).get("field") for r in results] == ["stage", "location", None]
    assert sum("photo_suggestion" in r for r in results) == 1


def test_no_photo_decline_before_symptom_never_requests_one(app_client):
    client, _ = app_client
    path = new_case(client)
    answer = client.post(path + "/messages", json={"text": "没有照片，小麦叶片发黄应该怎么观察？"}).json()
    assert answer["provider"] == "deepseek"
    assert "photo_suggestion" not in answer


def test_text_conversation_can_switch_crop_without_reusing_old_stage(app_client):
    client, generated = app_client
    path = new_case(client, crop="wheat", stage="拔节孕穗期")
    answer = client.post(path + "/messages", json={"text": "番茄种植需要注意哪些事项？"}).json()
    assert answer["provider"] == "deepseek"
    assert generated[0]["context"]["crop"] == "番茄"
    assert generated[0]["context"]["stage"] != "拔节孕穗期"


def test_original_message_retry_is_idempotent(app_client):
    client, generated = app_client
    path = new_case(client)
    body = {"text": "水稻种植需要注意什么？", "request_id": "same-network-retry"}
    first = client.post(path + "/messages", json=body)
    second = client.post(path + "/messages", json=body)
    assert first.json() == second.json() and len(generated) == 1
    assert len(client.get(path).json()["messages"]) == 2


def test_guest_messages_and_legacy_resume_are_unauthorized(app_client):
    client, generated = app_client
    path = new_case(client)
    guest = {"Authorization": "", "X-Client-ID": "other-test-guest"}
    assert client.post(path + "/messages", headers=guest, json={"text": "水稻怎么种？"}).status_code == 401
    assert client.post(path + "/resume", headers=guest, json={"question_id": "legacy"}).status_code == 401
    assert generated == []


def test_legacy_resume_answers_once_even_when_context_is_empty(app_client):
    client, generated = app_client
    path = new_case(client)
    question = seed_legacy_pending(client, path)
    client.get(path)
    client.post(path + "/context", json={"skip_context_fields": ["crop", "stage"]})
    assert generated == []
    result = client.post(path + "/resume", json={"question_id": question})
    assert result.status_code == 200 and result.json()["provider"] == "deepseek"
    assert generated[0]["text"] == "叶片有黄斑，如何观察？"
    assert "pending_question" not in client.get(path).json()
    again = client.post(path + "/resume", json={"question_id": question})
    assert again.json() == result.json() and len(generated) == 1


def test_new_question_supersedes_legacy_pending_question(app_client):
    client, generated = app_client
    path = new_case(client)
    question = seed_legacy_pending(client, path)
    client.post(path + "/messages", json={"text": "什么是小麦白粉病？"})
    assert len(generated) == 1 and generated[0]["text"] == "什么是小麦白粉病？"
    assert client.post(path + "/resume", json={"question_id": question}).status_code == 409


def test_concurrent_legacy_resume_is_locked_and_completed_result_replayed(app_client, monkeypatch):
    client, generated = app_client
    path = new_case(client)
    question = seed_legacy_pending(client, path)
    entered, finish = Event(), Event()
    original = client.app.state.chat.answer

    async def delayed(*args, **kwargs):
        entered.set()
        while not finish.is_set():
            await asyncio.sleep(0.01)
        return await original(*args, **kwargs)

    monkeypatch.setattr(client.app.state.chat, "answer", delayed)
    body = {"question_id": question}
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.post, path + "/resume", json=body)
        try:
            assert entered.wait(5)
            assert client.post(path + "/resume", json=body).status_code == 409
        finally:
            finish.set()
        completed = first.result(timeout=5)
    assert client.post(path + "/resume", json=body).json() == completed.json()
    assert len(generated) == 1


def test_empty_account_draft_is_not_listed_but_question_is(app_client):
    client, _ = app_client
    path = new_case(client)
    assert client.get("/api/cases").json()["items"] == []
    client.post(path + "/messages", json={"text": "水稻怎么种？"})
    assert len(client.get("/api/cases").json()["items"]) == 1


@pytest.mark.parametrize("question,field_question", [
    ("什么是番茄白粉病？", False),
    ("我家番茄叶片有黄斑，应该怎么观察？", True),
])
def test_cross_crop_text_ignores_old_image_without_blocking_answer(app_client, question, field_question):
    client, generated = app_client
    path = new_case(client, crop="wheat", stage="拔节孕穗期")
    store = client.app.state.store
    case_id = path.rsplit("/", 1)[-1]
    owner = store.owner_of(case_id)
    case = store.get(owner, case_id)
    case.update({
        "images": [{"id": "prior-wheat-image"}],
        "status": "identified",
        "disease_id": "wheat_powdery_mildew",
        "candidates": [{"id": "wheat_powdery_mildew", "name": "wheat powdery mildew", "score": 0.98}],
    })
    store.save(owner, case)
    answer = client.post(path + "/messages", json={"text": question}).json()
    assert answer["provider"] == "deepseek"
    context = generated[-1]["context"]
    assert context["response_policy"]["prior_photo_ignored"] is True
    assert context["recognition"]["image_received"] is False
    assert context["knowledge_coverage"]["recognized_disease_id"] is None
    assert context["stage"] != "拔节孕穗期"
    assert all(card["crop"] != "wheat" for card in context["knowledge"])
    assert "recognition" not in answer and "context_suggestion" not in answer
    assert "photo_suggestion" not in answer
    if field_question:
        assert "新建对应作物记录" in answer["notice"]
    original = client.get(path).json()
    assert original["crop"] == "wheat" and len(original["images"]) == 1

    # 代词追问不会重新套用原小麦照片；即便携带同记录图片 ID，也须明确隔离。
    followup = client.post(path + "/messages", json={"text": "那应该怎么处理？"}).json()
    assert followup["provider"] == "deepseek"
    context = generated[-1]["context"]
    assert context["response_policy"]["prior_photo_ignored"] is True
    assert context["recognition"]["image_received"] is False
    assert context["knowledge_coverage"]["recognized_disease_id"] is None
    assert "recognition" not in followup
    attached = client.post(path + "/messages", json={
        "text": "那应该怎么处理？", "image_ids": ["prior-wheat-image"],
    }).json()
    assert attached["provider"] == "deepseek" and "recognition" not in attached
    assert generated[-1]["context"]["recognition"]["image_received"] is False


def test_followup_on_crop_without_vision_model_keeps_its_knowledge_scope(app_client):
    client, generated = app_client
    path = new_case(client)
    client.post(path + "/messages", json={"text": "番茄白粉病怎么防治？"})
    answer = client.post(path + "/messages", json={"text": "白粉病应该怎么预防？"}).json()
    assert answer["provider"] == "deepseek"
    context = generated[-1]["context"]
    assert context["crop"] == "番茄"
    assert all(card["crop"] != "wheat" for card in context["knowledge"])
    assert "context_suggestion" not in answer
