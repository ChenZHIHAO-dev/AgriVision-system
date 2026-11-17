"""User intent survives program-only context collection and is resumed exactly once."""

from pathlib import Path

import pytest
from app.config import Settings
from app.context import follow_up
from app.main import create_app
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
OWNER = {"X-Client-ID": "intake-test-owner"}
OTHER = {"X-Client-ID": "intake-other-owner"}


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    app = create_app(Settings(root=ROOT, runtime=tmp_path, models=tmp_path / "models"))
    generated = []

    async def answer(
        case, text, history, model=None, thinking=False, *, web_search=False
    ):
        if follow_up(case):
            return {
                "provider": "clarification",
                "text": "补充基本信息",
                "sources": [],
                "products": [],
                "follow_up": follow_up(case),
            }
        generated.append(
            {
                "text": text,
                "stage": case["stage"],
                "crop": case["crop"],
                "model": model,
                "thinking": thinking,
                "web_search": web_search,
            }
        )
        return {
            "provider": "deepseek",
            "text": "针对原问题的回答：" + text,
            "sources": [],
            "products": [],
        }

    monkeypatch.setattr(app.state.chat, "answer", answer)
    with TestClient(app) as client:
        yield client, generated


def new_case(client, **fields):
    case = client.post("/api/consultations", headers=OWNER, json=fields).json()
    return "/api/cases/" + case["id"]


def test_final_context_resumes_original_question_once_without_synthetic_user(
    app_client,
):
    client, generated = app_client
    path = new_case(client)
    client.post(
        path + "/messages",
        headers=OWNER,
        json={"text": "叶片有斑点，如何解决？", "request_id": "original"},
    )
    first = client.get(path, headers=OWNER).json()
    pending = first["pending_question"]["id"]
    for data in ({"crop": "wheat"}, {"stage": "苗期"}):
        assert (
            client.post(path + "/context", headers=OWNER, json=data).status_code == 200
        )
        assert generated == []
    result = client.post(
        path + "/resume",
        headers=OWNER,
        json={"question_id": pending, "model": "deepseek-v4-pro", "thinking": True},
    )
    assert result.status_code == 200
    assert generated == [
        {
            "text": "叶片有斑点，如何解决？",
            "crop": "wheat",
            "stage": "苗期",
            "model": "deepseek-v4-pro",
            "thinking": True,
            "web_search": False,
        }
    ]
    again = client.post(path + "/resume", headers=OWNER, json={"question_id": pending})
    assert again.json() == result.json() and len(generated) == 1
    final = client.get(path, headers=OWNER).json()
    assert "pending_question" not in final
    assert [m["text"] for m in final["messages"] if m["role"] == "user"] == [
        "叶片有斑点，如何解决？"
    ]


def test_early_resume_and_metadata_only_never_generate(app_client):
    client, generated = app_client
    path = new_case(client, crop="wheat")
    client.post(path + "/context", headers=OWNER, json={"location": "南阳"})
    response = client.post(
        path + "/messages", headers=OWNER, json={"text": "如何处理叶片发黄？"}
    )
    pending = response.json()["pending_question_id"]
    assert (
        client.post(
            path + "/resume", headers=OWNER, json={"question_id": pending}
        ).json()["provider"]
        == "clarification"
    )
    assert generated == []
    client.post(path + "/context", headers=OWNER, json={"stage": "暂不确定"})
    assert (
        client.post(
            path + "/resume", headers=OWNER, json={"question_id": pending}
        ).json()["provider"]
        == "deepseek"
    )
    assert len(generated) == 1


def test_typed_context_continues_the_question_instead_of_answering_the_field(
    app_client,
):
    client, generated = app_client
    path = new_case(client)
    client.post(path + "/messages", headers=OWNER, json={"text": "叶片白斑如何处理？"})
    client.post(path + "/messages", headers=OWNER, json={"text": "是小麦"})
    assert generated == []
    response = client.post(
        path + "/messages", headers=OWNER, json={"text": "现在是苗期"}
    )
    assert response.json()["provider"] == "deepseek"
    assert generated[0]["text"] == "叶片白斑如何处理？"


def test_new_question_supersedes_old_and_stale_resume_is_rejected(app_client):
    client, generated = app_client
    path = new_case(client, crop="wheat")
    old = client.post(
        path + "/messages", headers=OWNER, json={"text": "白斑如何处理？"}
    ).json()["pending_question_id"]
    new = client.post(
        path + "/messages", headers=OWNER, json={"text": "我现在想问如何拍清楚照片？"}
    ).json()["pending_question_id"]
    assert old != new
    client.post(path + "/context", headers=OWNER, json={"stage": "苗期"})
    assert (
        client.post(
            path + "/resume", headers=OWNER, json={"question_id": old}
        ).status_code
        == 409
    )
    client.post(path + "/resume", headers=OWNER, json={"question_id": new})
    assert len(generated) == 1 and generated[0]["text"] == "我现在想问如何拍清楚照片？"


def test_pending_questions_and_resume_are_owner_scoped(app_client):
    client, generated = app_client
    path = new_case(client, crop="wheat")
    question = client.post(
        path + "/messages", headers=OWNER, json={"text": "如何解决？"}
    ).json()["pending_question_id"]
    assert client.get(path, headers=OTHER).status_code == 404
    assert (
        client.post(
            path + "/resume", headers=OTHER, json={"question_id": question}
        ).status_code
        == 404
    )
    assert generated == []


def test_original_message_retry_is_idempotent(app_client):
    client, generated = app_client
    path = new_case(client, crop="wheat", stage="苗期")
    body = {"text": "叶片白斑如何处理？", "request_id": "same-network-retry"}
    first = client.post(path + "/messages", headers=OWNER, json=body)
    second = client.post(path + "/messages", headers=OWNER, json=body)
    assert first.json() == second.json() and len(generated) == 1
    assert len(client.get(path, headers=OWNER).json()["messages"]) == 2


def test_empty_account_draft_is_not_listed_but_question_is(app_client):
    client, _ = app_client
    account = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()
    headers = {"Authorization": "Bearer " + account["access_token"]}
    record = client.post("/api/consultations", headers=headers, json={}).json()
    assert client.get("/api/cases", headers=headers).json()["items"] == []
    client.post(
        "/api/cases/" + record["id"] + "/messages",
        headers=headers,
        json={"text": "叶片怎么发黄了？"},
    )
    assert len(client.get("/api/cases", headers=headers).json()["items"]) == 1


def test_concurrent_resume_is_locked_then_completed_request_is_replayed(
    app_client, monkeypatch
):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    client, generated = app_client
    path = new_case(client, crop="wheat")
    question = client.post(
        path + "/messages", headers=OWNER, json={"text": "如何处理？"}
    ).json()["pending_question_id"]
    client.post(path + "/context", headers=OWNER, json={"stage": "苗期"})
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
        first = pool.submit(client.post, path + "/resume", headers=OWNER, json=body)
        try:
            assert entered.wait(5)
            assert (
                client.post(path + "/resume", headers=OWNER, json=body).status_code
                == 409
            )
        finally:
            finish.set()
        completed = first.result(timeout=5)
    assert (
        client.post(path + "/resume", headers=OWNER, json=body).json()
        == completed.json()
    )
    assert len(generated) == 1


def test_pending_question_persists_with_account_case_across_server_restart(
    app_client, monkeypatch
):
    client, generated = app_client
    login = {"username": "admin", "password": "admin123"}
    token = client.post("/api/auth/login", json=login).json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    record = client.post(
        "/api/consultations", headers=headers, json={"crop": "wheat"}
    ).json()
    path = "/api/cases/" + record["id"]
    question = client.post(
        path + "/messages", headers=headers, json={"text": "叶片白斑如何处理？"}
    ).json()["pending_question_id"]
    restarted = create_app(
        Settings(
            root=ROOT,
            runtime=client.app.state.store.path.parent,
            models=ROOT / "missing-test-models",
        )
    )
    monkeypatch.setattr(restarted.state.chat, "answer", client.app.state.chat.answer)
    with TestClient(restarted) as second:
        fresh_token = second.post("/api/auth/login", json=login).json()["access_token"]
        new_headers = {"Authorization": "Bearer " + fresh_token}
        assert (
            second.get(path, headers=new_headers).json()["pending_question"]["id"]
            == question
        )
        second.post(path + "/context", headers=new_headers, json={"stage": "苗期"})
        assert (
            second.post(
                path + "/resume", headers=new_headers, json={"question_id": question}
            ).status_code
            == 200
        )
    assert len(generated) == 1
