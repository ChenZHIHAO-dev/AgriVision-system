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
        assert len(client.get(path, headers=headers).json()["messages"]) == 2
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
