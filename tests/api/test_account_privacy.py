from io import BytesIO
from pathlib import Path
from fastapi.testclient import TestClient
import numpy as np
import pytest
from PIL import Image

from app.config import Settings
from app.application import create_app

ROOT = Path(__file__).resolve().parents[2]


def app_at(tmp_path, admin_hash=""):
    return create_app(
        Settings(
            root=ROOT,
            runtime=tmp_path / "runtime",
            models=tmp_path / "models",
            admin_password_hash=admin_hash,
        )
    )


def picture():
    stream = BytesIO()
    Image.fromarray(
        np.random.default_rng(9).integers(25, 225, (400, 500, 3), dtype=np.uint8)
    ).save(stream, "JPEG")
    return stream.getvalue()


def test_guest_can_recognize_but_cannot_call_consultation_provider(tmp_path, monkeypatch):
    app = app_at(tmp_path)
    headers = {"X-Client-ID": "temporary-guest-session"}

    async def unexpected_provider(*args, **kwargs):
        pytest.fail("An unsigned request reached the consultation provider")

    monkeypatch.setattr(app.state.chat, "answer", unexpected_provider)
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
        for route, body in (
            ("/api/consultations", {"crop": "wheat"}),
            (path + "/messages", {"text": "叶片需要观察什么？"}),
            (path + "/resume", {"question_id": "pending-test-question"}),
        ):
            response = client.post(route, headers=headers, json=body)
            assert response.status_code == 401
        upload = client.post(
            path + "/attachments", headers=headers, files={"file": ("notes.txt", b"test")}
        )
        assert upload.status_code == 401
        assert client.delete(path + "/attachments/old", headers=headers).status_code == 401
        assert len(client.get(path, headers=headers).json()["messages"]) == 2
        assert client.get("/api/cases", headers=headers).json()["items"] == []
        with app.state.store.persistent.connection() as db:
            assert db.execute("SELECT count(*) FROM cases").fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 0
        assert not (tmp_path / "runtime/images").exists()
        assert client.post(
            "/api/guest/end", json={"client_id": headers["X-Client-ID"]}
        ).status_code == 204
        assert client.get(path, headers=headers).status_code == 404
        assert client.get(record["images"][0]["url"]).status_code == 404


def test_account_records_follow_server_identity_across_clients_and_survive_restart(
    tmp_path, account_headers, admin_hash,
):
    app = app_at(tmp_path, admin_hash)
    with TestClient(app) as client:
        authorization = {**account_headers(client), "X-Client-ID": "first-device-client"}
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
    with TestClient(app_at(tmp_path, admin_hash)) as restarted:
        stored = restarted.get("/api/cases", headers=account_headers(restarted)).json()["items"]
        assert stored[0]["id"] == record["id"] and len(stored[0]["messages"]) == 2


@pytest.mark.parametrize("admin_hash_value", ["", "plain-fake-password", "invalid:hash"])
def test_unconfigured_admin_login_fails_without_blocking_guest_api(tmp_path, admin_hash_value):
    with TestClient(app_at(tmp_path, admin_hash_value)) as client:
        assert client.get("/api/health").status_code == 200
        response = client.post(
            "/api/auth/login", json={"username": "admin", "password": "test-account"}
        )
        assert response.status_code == 503
        assert "access_token" not in response.json()


def test_only_admin_can_login_and_registration_keeps_guest_record(tmp_path, admin_hash, account_headers):
    app = app_at(tmp_path, admin_hash)
    guest = {"X-Client-ID": "register-guest-session"}
    with TestClient(app) as client:
        record = client.post(
            "/api/cases",
            headers=guest,
            data={"crop": "wheat"},
            files={"file": ("leaf.jpg", picture(), "image/jpeg")},
        ).json()
        response = client.post(
            "/api/auth/register", headers=guest, json={"continue_case_id": record["id"]}
        )
        assert response.status_code == 403
        assert client.post(
            "/api/auth/login", json={"username": "grower", "password": "test-account"}
        ).status_code == 401
        assert client.get("/api/cases/" + record["id"], headers=guest).status_code == 200
        me = client.get("/api/auth/me", headers=account_headers(client)).json()
        assert me["user"]["id"] == "dev-admin" and me["user"]["role"] == "admin"
        assert me["account_provider"] == "configured-admin"


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
    tmp_path, monkeypatch, account_headers, admin_hash
):
    from dataclasses import replace
    import httpx
    from app.chat import Chat

    app = app_at(tmp_path, admin_hash)
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
    with TestClient(app) as client:
        headers = account_headers(client)
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


def test_unsent_photo_can_be_removed_but_sent_evidence_is_retained(tmp_path, account_headers, admin_hash):
    app = app_at(tmp_path, admin_hash)
    with TestClient(app) as client:
        headers = account_headers(client)
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



def test_auth_continues_only_the_selected_photo_case(tmp_path, admin_hash):
    app = app_at(tmp_path, admin_hash)
    guest = {"X-Client-ID": "handoff-own-guest"}
    other_guest = {"X-Client-ID": "handoff-other-guest"}
    credentials = {"username": "admin", "password": "test-account"}

    with TestClient(app) as client:
        case = client.post(
            "/api/cases",
            headers=guest,
            data={"crop": "wheat", "stage": "苗期"},
            files={"file": ("leaf.jpg", picture(), "image/jpeg")},
        ).json()
        path = "/api/cases/" + case["id"]
        case = client.post(
            path + "/images",
            headers=guest,
            files={"file": ("extra.jpg", picture(), "image/jpeg")},
        ).json()
        other_case = client.post(
            "/api/cases",
            headers=other_guest,
            data={"crop": "wheat"},
            files={"file": ("other.jpg", picture(), "image/jpeg")},
        ).json()
        original_images = [client.get(photo["url"]).content for photo in case["images"]]
        store = app.state.store
        guest_owner = store.owner_of(case["id"])
        assert guest_owner.startswith("g_") and guest["X-Client-ID"] not in guest_owner
        stale_case = store.get(guest_owner, case["id"])
        stale_case["documents"] = [{"id": "old-notes", "text": "旧访客资料"}]
        stale_case["pending_question"] = {"id": "old-question"}
        store.save(guest_owner, stale_case)
        store.add_message(case["id"], {"role": "assistant", "provider": "knowledge"})

        failed = client.post(
            "/api/auth/login",
            headers=guest,
            json={**credentials, "password": "bad-password", "continue_case_id": case["id"]},
        )
        assert failed.status_code == 401

        blocked = client.post(
            "/api/auth/login",
            headers=guest,
            json={**credentials, "continue_case_id": other_case["id"]},
        )
        assert blocked.status_code == 404
        assert client.get(path, headers=guest).status_code == 200

        accepted = client.post(
            "/api/auth/login",
            headers=guest,
            json={**credentials, "continue_case_id": case["id"]},
        )
        assert accepted.status_code == 200
        result = accepted.json()
        assert result["continued_case_id"] == case["id"]
        account = {"Authorization": "Bearer " + result["access_token"]}
        continued = client.get(path, headers=account).json()
        assert continued["persistence"] == "account"
        assert continued["documents"] == [] and "pending_question" not in continued
        assert continued["recognition"] == case["recognition"]
        assert continued["messages"] == case["messages"]
        assert [client.get(photo["url"]).content for photo in continued["images"]] == original_images
        assert all(client.get(photo["url"]).status_code == 404 for photo in case["images"])
        assert client.get(path, headers=guest).status_code == 404
        assert [item["id"] for item in client.get("/api/cases", headers=account).json()["items"]] == [case["id"]]
        assert client.get("/api/cases/" + other_case["id"], headers=other_guest).status_code == 200
        assert client.get(path, headers=other_guest).status_code == 404



def test_case_write_failure_preserves_guest_photo_and_can_be_retried(
    tmp_path, monkeypatch, account_headers, admin_hash
):
    app = app_at(tmp_path, admin_hash)
    persistence = app.state.store.persistent
    guest = {"X-Client-ID": "handoff-guest-retry"}

    def interrupted(*args):
        raise OSError("simulated store failure")

    with TestClient(app, raise_server_exceptions=False) as client:
        account = account_headers(client)
        case = client.post(
            "/api/cases",
            headers=guest,
            data={"crop": "wheat"},
            files={"file": ("leaf.jpg", picture(), "image/jpeg")},
        ).json()
        case_id = case["id"]
        path = "/api/cases/" + case_id
        payload = {
            "username": "admin",
            "password": "test-account",
            "continue_case_id": case_id,
        }
        with monkeypatch.context() as patch:
            patch.setattr(persistence, "insert_case_with_messages", interrupted)
            assert client.post("/api/auth/login", headers=guest, json=payload).status_code == 500
        assert client.get(path, headers=guest).status_code == 200
        assert client.get(case["images"][0]["url"]).status_code == 200
        assert client.get(path, headers=account).status_code == 404
        assert not (persistence.path.parent / "images" / case_id).exists()
        assert client.post("/api/auth/login", headers=guest, json=payload).json()["continued_case_id"] == case_id
