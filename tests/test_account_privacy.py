from io import BytesIO
from pathlib import Path
from fastapi.testclient import TestClient
import numpy as np
from PIL import Image

from app.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def app_at(tmp_path):
    return create_app(
        Settings(root=ROOT, runtime=tmp_path / "runtime", models=tmp_path / "models")
    )


def picture():
    stream = BytesIO()
    Image.fromarray(
        np.random.default_rng(9).integers(25, 225, (400, 500, 3), dtype=np.uint8)
    ).save(stream, "JPEG")
    return stream.getvalue()


def test_guest_questions_and_images_never_reach_persistent_storage(tmp_path):
    app = app_at(tmp_path)
    headers = {"X-Client-ID": "temporary-guest-session"}
    with TestClient(app) as client:
        record = client.post(
            "/api/cases",
            headers=headers,
            data={"crop": "wheat"},
            files={"file": ("test.jpg", picture(), "image/jpeg")},
        ).json()
        path = "/api/cases/" + record["id"]
        assert record["persistence"] == "temporary"
        assert client.get(record["images"][0]["url"]).status_code == 200
        assert (
            client.post(
                path + "/messages", headers=headers, json={"text": "叶片需要观察什么？"}
            ).status_code
            == 201
        )
        assert len(client.get(path, headers=headers).json()["messages"]) == 4
        assert client.get("/api/cases", headers=headers).json()["items"] == []
        with app.state.store.persistent.connection() as db:
            assert db.execute("SELECT count(*) FROM cases").fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 0
        assert not (tmp_path / "runtime/images").exists()
        client.post("/api/guest/end", headers=headers, json={})
        assert client.get(path, headers=headers).status_code == 404
        assert client.get(record["images"][0]["url"]).status_code == 404


def test_account_records_follow_server_identity_across_clients_and_survive_restart(
    tmp_path,
):
    app = app_at(tmp_path)
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin123"}
        ).json()
        authorization = {
            "Authorization": "Bearer " + login["access_token"],
            "X-Client-ID": "first-device-client",
        }
        record = client.post(
            "/api/consultations",
            headers=authorization,
            json={"crop": "wheat", "stage": "苗期"},
        ).json()
        assert record["persistence"] == "account"
        client.post(
            "/api/cases/" + record["id"] + "/messages",
            headers=authorization,
            json={"text": "怎样记录田间症状？"},
        )
        second = {**authorization, "X-Client-ID": "second-device-client"}
        assert (
            client.get("/api/cases", headers=second).json()["items"][0]["id"]
            == record["id"]
        )
        assert client.get("/api/admin/status", headers=authorization).status_code == 200
        assert (
            client.get(
                "/api/cases/" + record["id"], headers={"X-Client-ID": "u_dev-admin"}
            ).status_code
            == 404
        )
        client.post("/api/auth/logout", headers=authorization)
        assert client.get("/api/cases", headers=authorization).status_code == 401
    with TestClient(app_at(tmp_path)) as restarted:
        token = restarted.post(
            "/api/auth/login", json={"username": "admin", "password": "admin123"}
        ).json()["access_token"]
        stored = restarted.get(
            "/api/cases", headers={"Authorization": "Bearer " + token}
        ).json()["items"]
        assert stored[0]["id"] == record["id"] and len(stored[0]["messages"]) == 2


def test_registration_does_not_grant_admin_or_inherit_guest_history(tmp_path):
    app = app_at(tmp_path)
    guest = {"X-Client-ID": "register-guest-session"}
    with TestClient(app) as client:
        record = client.post(
            "/api/consultations", headers=guest, json={"crop": "wheat"}
        ).json()
        response = client.post(
            "/api/auth/register",
            headers=guest,
            json={"name": "测试农户", "username": "grower", "password": "test1234"},
        )
        assert response.status_code == 201
        session = response.json()
        headers = {"Authorization": "Bearer " + session["access_token"]}
        assert session["user"]["role"] == "member"
        assert client.get("/api/cases", headers=headers).json()["items"] == []
        assert (
            client.get("/api/cases/" + record["id"], headers=guest).status_code == 404
        )
        assert client.get("/api/admin/status", headers=headers).status_code == 403
        assert (
            client.post(
                "/api/auth/register",
                json={"name": "其他人", "username": "admin", "password": "test1234"},
            ).status_code
            == 422
        )


def test_active_guest_images_share_context_expiry_and_eviction_never_writes_messages(
    tmp_path, monkeypatch
):
    from app.repository import CaseRepository

    clock = [1000]
    monkeypatch.setattr("app.repository.time.time", lambda: clock[0])
    store = CaseRepository(tmp_path / "records.sqlite")
    store.ttl = 10
    owner, case_id = "g_temporary-test", "temporary-case"
    store.put_image(owner, case_id, "photo", b"photo")
    store.save(owner, {"id": case_id})
    clock[0] = 1009
    assert store.get(owner, case_id)
    clock[0] = 1011
    assert store.get_image(owner, case_id, "photo") == b"photo"
    store.clear_guest(owner)
    store.add_exchange(case_id, {"role": "user"}, {"role": "assistant"})
    with store.persistent.connection() as db:
        assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 0


def test_retry_reuses_temporary_image_and_never_calls_chat(tmp_path, monkeypatch):
    app = app_at(tmp_path)
    headers = {"X-Client-ID": "retry-guest-session"}
    with TestClient(app) as client:
        record = client.post(
            "/api/cases",
            headers=headers,
            data={"crop": "wheat"},
            files={"file": ("test.jpg", picture(), "image/jpeg")},
        ).json()
        seen = []

        def predict(crop, source):
            seen.append((crop, source.read(3)))
            return {
                "status": "identified",
                "title": "疑似小麦白粉病",
                "disease_id": "wheat_powdery_mildew",
                "model_version": "test-retry",
                "candidates": [
                    {"id": "wheat_powdery_mildew", "name": "小麦白粉病", "score": 0.99}
                ],
            }

        monkeypatch.setattr(app.state.registry, "predict", predict)

        async def no_chat(*args, **kwargs):
            raise AssertionError("standalone recognition must not call DeepSeek")

        monkeypatch.setattr(app.state.chat, "answer", no_chat)
        result = client.post("/api/cases/" + record["id"] + "/retry", headers=headers)
        assert result.status_code == 200
        body = result.json()
        assert body["recognition"]["outcome"] == "consistent_support"
        assert len(body["images"]) == 1 and len(body["versions"]) == 2
        assert (
            len(body["messages"]) == 2
            and body["messages"][1]["provider"] == "recognition"
        )
        assert seen == [("wheat", b"\xff\xd8\xff")]
        assert not (tmp_path / "runtime/images").exists()


def test_basic_context_choices_never_call_provider_until_user_asks_again(
    tmp_path, monkeypatch
):
    from dataclasses import replace
    import httpx
    from app.chat import Chat

    app = app_at(tmp_path)
    app.state.chat.settings = replace(
        app.state.chat.settings, deepseek_key="fake-test-value"
    )
    called = []

    async def provider(self, url, **kwargs):
        called.append(kwargs["json"])
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "先记录叶片症状和田间分布。"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", provider)
    headers = {"X-Client-ID": "context-only-session"}
    with TestClient(app) as client:
        case = client.post("/api/consultations", headers=headers, json={}).json()
        path = "/api/cases/" + case["id"]
        first = client.post(
            path + "/messages", headers=headers, json={"text": "叶片有斑点，怎么排查？"}
        ).json()
        assert first["provider"] == "clarification" and not called
        client.post(path + "/context", headers=headers, json={"crop": "wheat"})
        second = client.post(
            path + "/messages", headers=headers, json={"text": "先说明排查方向"}
        ).json()
        assert second["provider"] == "clarification" and not called
        client.post(path + "/context", headers=headers, json={"stage": "暂不确定"})
        assert not called
        final = client.post(
            path + "/messages", headers=headers, json={"text": "请回答刚才的问题。"}
        ).json()
        assert final["provider"] == "deepseek" and len(called) == 1


def test_unsent_photo_can_be_removed_but_sent_evidence_is_retained(tmp_path):
    app = app_at(tmp_path)
    headers = {"X-Client-ID": "unsent-photo-session"}
    with TestClient(app) as client:
        consultation = client.post(
            "/api/consultations", headers=headers, json={"crop": "wheat"}
        ).json()
        case = client.post(
            "/api/cases/" + consultation["id"] + "/images",
            headers=headers,
            files={"file": ("leaf.jpg", picture(), "image/jpeg")},
        ).json()
        path = "/api/cases/" + case["id"]
        photo = case["images"][0]
        deleted = client.delete(path + "/images/" + photo["id"], headers=headers).json()
        assert not deleted["images"] and not deleted["recognition"]["image_received"]
        assert client.get(photo["url"]).status_code == 404
        case = client.post(
            path + "/images",
            headers=headers,
            files={"file": ("leaf.jpg", picture(), "image/jpeg")},
        ).json()
        photo = case["images"][0]
        client.post(
            path + "/messages",
            headers=headers,
            json={"text": "这张照片需要补拍吗？", "image_ids": [photo["id"]]},
        )
        assert (
            client.delete(path + "/images/" + photo["id"], headers=headers).status_code
            == 409
        )
