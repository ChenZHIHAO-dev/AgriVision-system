"""真实 SQLite 会话生命周期；重建服务而不是复用进程内认证对象。"""

import hashlib
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.application import create_app
from app.auth import ADMIN_USER, AuthManager, hash_admin_password
from app.config import Settings
from app.store import Store

ROOT = Path(__file__).resolve().parents[2]


def auth_at(path, password_hash):
    return AuthManager(password_hash, database=Store(path))


def login(client, *, remember=True, password="test-account", **extra):
    response = client.post("/api/auth/login", json={
        "username": "admin", "password": password, "remember": remember, **extra,
    })
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def photo():
    output = BytesIO()
    Image.new("RGB", (320, 320), "#507c40").save(output, "JPEG")
    return output.getvalue()


def test_only_remembered_token_digest_is_persisted_and_migration_is_idempotent(tmp_path, admin_hash):
    path = tmp_path / "records.sqlite3"
    original = auth_at(path, admin_hash)
    remembered = original.login("admin", "test-account", remember=True)
    temporary = original.login("admin", "test-account")
    with original.sessions.database.connection() as db:
        rows = db.execute("SELECT * FROM auth_sessions").fetchall()
        assert len(rows) == 1
        assert rows[0]["token_digest"] == hashlib.sha256(remembered["access_token"].encode()).hexdigest()
        assert rows[0]["expires_at"] == remembered["expires_at"]
        # 数据库中只有摘要；密码哈希配置和原始 token 都不能被转存进来。
        dump = "\n".join(db.iterdump())
        for secret in (remembered["access_token"], temporary["access_token"], admin_hash):
            assert secret not in dump
    restarted = auth_at(path, admin_hash)
    assert restarted.verify(remembered["access_token"]) == ADMIN_USER
    assert restarted.verify(temporary["access_token"]) is None
    assert original.verify(temporary["access_token"]) == ADMIN_USER
    assert restarted.signing_key == original.signing_key
    assert auth_at(path, admin_hash).verify(remembered["access_token"]) == ADMIN_USER


@pytest.mark.parametrize("remember,lifetime", [(False, 8 * 3600), (True, 7 * 86400)])
def test_exact_expiry_revokes_session_and_longer_lived_image_grant(
    tmp_path, admin_hash, monkeypatch, remember, lifetime,
):
    clock = [1000.0]
    monkeypatch.setattr("app.auth.time.time", lambda: clock[0])
    auth = auth_at(tmp_path / "records.sqlite3", admin_hash)
    session = auth.login("admin", "test-account", remember=remember)
    assert session["expires_at"] == clock[0] + lifetime
    clock[0] = session["expires_at"] - 1
    image_token = auth.image_token("u_dev-admin", "case", "photo", session["access_token"])
    assert auth.verify(session["access_token"]) == ADMIN_USER
    assert auth.image_owner(image_token, "case", "photo") == "u_dev-admin"
    clock[0] = session["expires_at"]
    assert auth.verify(session["access_token"]) is None
    assert auth.image_owner(image_token, "case", "photo") is None
    with auth.sessions.database.connection() as db:
        assert db.execute("SELECT count(*) FROM auth_sessions").fetchone()[0] == 0


def test_image_short_link_expires_before_remembered_session(tmp_path, admin_hash, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("app.auth.time.time", lambda: clock[0])
    path = tmp_path / "records.sqlite3"
    auth = auth_at(path, admin_hash)
    session = auth.login("admin", "test-account", remember=True)
    grant = auth.image_token("u_dev-admin", "case", "photo", session["access_token"])
    clock[0] += 900
    restarted = auth_at(path, admin_hash)
    assert restarted.verify(session["access_token"]) == ADMIN_USER
    assert restarted.image_owner(grant, "case", "photo") is None


def test_logout_is_immediate_across_managers_but_keeps_other_sessions(tmp_path, admin_hash):
    path = tmp_path / "records.sqlite3"
    original = auth_at(path, admin_hash)
    first = original.login("admin", "test-account", remember=True)
    second = original.login("admin", "test-account", remember=True)
    grant = original.image_token("u_dev-admin", "case", "photo", first["access_token"])
    restarted = auth_at(path, admin_hash)
    assert restarted.image_owner(grant, "case", "photo") == "u_dev-admin"
    restarted.logout(first["access_token"])
    for auth in (original, restarted, auth_at(path, admin_hash)):
        assert auth.verify(first["access_token"]) is None
        assert auth.image_owner(grant, "case", "photo") is None
        assert auth.verify(second["access_token"]) == ADMIN_USER


def test_password_rotation_revokes_old_generation_and_stale_manager_cannot_issue(
    tmp_path, admin_hash,
):
    path = tmp_path / "records.sqlite3"
    old = auth_at(path, admin_hash)
    remembered = old.login("admin", "test-account", remember=True)
    temporary = old.login("admin", "test-account")
    grant = old.image_token("u_dev-admin", "case", "photo", remembered["access_token"])
    changed_hash = hash_admin_password("changed-test-password")
    current = auth_at(path, changed_hash)
    assert current.signing_key != old.signing_key
    fresh = current.login("admin", "changed-test-password", remember=True)
    for auth in (old, current):
        assert auth.verify(remembered["access_token"]) is None
        assert auth.verify(temporary["access_token"]) is None
        assert auth.image_owner(grant, "case", "photo") is None
    with pytest.raises(RuntimeError, match="登录配置已更新"):
        old.login("admin", "test-account", remember=True)
    with current.sessions.database.connection() as db:
        assert db.execute("SELECT count(*) FROM auth_sessions").fetchone()[0] == 1
    assert current.verify(fresh["access_token"]) == ADMIN_USER
    # 即使重新使用旧密码哈希，也必须是新的随机代际；旧对象不得复活。
    reverted = auth_at(path, admin_hash)
    assert reverted.signing_key not in (old.signing_key, current.signing_key)
    assert old.verify(temporary["access_token"]) is None
    assert reverted.verify(fresh["access_token"]) is None
    with pytest.raises(RuntimeError):
        old.login("admin", "test-account")


def test_invalidated_password_configuration_also_revokes_remembered_sessions(tmp_path, admin_hash):
    path = tmp_path / "records.sqlite3"
    old = auth_at(path, admin_hash)
    token = old.login("admin", "test-account", remember=True)["access_token"]
    unconfigured = auth_at(path, "")
    assert unconfigured.verify(token) is None and old.verify(token) is None
    with pytest.raises(RuntimeError):
        old.login("admin", "test-account", remember=True)
    with pytest.raises(RuntimeError, match="尚未配置"):
        unconfigured.login("admin", "test-account")


@pytest.fixture
def settings(tmp_path, admin_hash):
    return Settings(root=ROOT, runtime=tmp_path, models=tmp_path / "models",
                    admin_password_hash=admin_hash)


def test_application_restart_preserves_remembered_identity_photos_and_history(settings):
    with TestClient(create_app(settings)) as client:
        remembered = login(client)
        temporary = login(client, remember=False)
        response = client.post("/api/cases", headers=remembered, data={"crop": "wheat"},
                               files={"file": ("photo.jpg", photo(), "image/jpeg")})
        assert response.status_code == 201
        record = response.json()
        image = record["images"][0]
        assert client.get(image["url"]).status_code == 200
        count = len(record["messages"])
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get("/api/auth/me", headers=remembered).json()["user"] == ADMIN_USER
        assert restarted.get("/api/auth/me", headers=temporary).status_code == 401
        restored = restarted.get("/api/cases/" + record["id"], headers=remembered).json()
        assert restored["persistence"] == "account" and len(restored["messages"]) == count
        assert restarted.get(image["url"]).status_code == 200
        assert restarted.get(image["url"].replace(image["id"], "different")).status_code == 401
        grant = image["url"].split("access_token=")[1]
        assert restarted.get("/api/knowledge?access_token=" + grant).status_code == 401
        assert restarted.delete(image["url"]).status_code == 401
        assert restarted.get("/api/admin/status", headers=remembered).json()["session_storage"] == "sqlite-remember"
        assert restarted.post("/api/auth/logout", headers=remembered).status_code == 204
        assert restarted.get(image["url"]).status_code == 401
    with TestClient(create_app(settings)) as again:
        assert again.get("/api/auth/me", headers=remembered).status_code == 401
        assert again.get(image["url"]).status_code == 401
        new_session = login(again)
        assert again.get("/api/cases/" + record["id"], headers=new_session).status_code == 200


def test_password_change_rejects_old_api_session_and_image_without_deleting_record(settings):
    original = create_app(settings)
    with TestClient(original) as client:
        old_headers = login(client)
        record = client.post("/api/cases", headers=old_headers, data={"crop": "wheat"},
                             files={"file": ("photo.jpg", photo(), "image/jpeg")}).json()
        new_hash = hash_admin_password("changed-test-password")
        with TestClient(create_app(replace(settings, admin_password_hash=new_hash))) as changed:
            assert changed.get("/api/auth/me", headers=old_headers).status_code == 401
            assert changed.get(record["images"][0]["url"]).status_code == 401
            assert client.get("/api/auth/me", headers=old_headers).status_code == 401
            old_login = client.post("/api/auth/login", json={
                "username": "admin", "password": "test-account", "remember": True,
            })
            assert old_login.status_code == 503
            assert changed.post("/api/auth/register", json={}).status_code == 403
            new_headers = login(changed, password="changed-test-password")
            restored = changed.get("/api/cases/" + record["id"], headers=new_headers).json()
            assert changed.get(restored["images"][0]["url"]).status_code == 200
            assert restored["id"] == record["id"]


def test_failed_login_continuation_revokes_new_persistent_session(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={
            "username": "admin", "password": "test-account", "remember": True,
            "continue_case_id": "0" * 32,
        })
        assert response.status_code == 404 and "access_token" not in response.json()
        with app.state.store.persistent.connection() as db:
            assert db.execute("SELECT count(*) FROM auth_sessions").fetchone()[0] == 0


def test_extracted_account_routes_keep_temporary_record_handoff(tmp_path, admin_hash):
    from contextlib import nullcontext

    from fastapi import FastAPI, Request
    from app.account_routes import create_account_router
    from app.repository import CaseRepository

    store = CaseRepository(tmp_path / "records.sqlite3")
    auth = AuthManager(admin_hash, database=store.persistent)
    owner = auth.guest_owner("legacy-client-id")
    case_id, image_id = "a" * 32, "photo"
    store.put_image(owner, case_id, image_id, b"photo-bytes")
    store.save(owner, {
        "id": case_id, "created_at": "2026-01-01", "updated_at": "2026-01-01",
        "images": [{"id": image_id}], "documents": [{"text": "temporary document"}],
        "pending_question": "old unsent question",
    })
    store.add_exchange(case_id, {"role": "user", "provider": "photo"},
                       {"role": "assistant", "provider": "recognition"})
    store.add_message(case_id, {"role": "user", "provider": "draft"})
    app = FastAPI()

    @app.middleware("http")
    async def legacy_server_context(request: Request, call_next):
        # 仅为模块兼容测试注入已确认的旧临时身份；正式应用仍由 access 统一拒绝匿名业务。
        request.state.owner = owner
        request.state.viewer = None
        request.state.token = ""
        return await call_next(request)

    app.include_router(create_account_router(
        auth=auth, store=store, mutation=lambda _case: nullcontext(),
        version="test", model_status=lambda: {}, deepseek_configured=lambda: False,
    ))
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={
            "username": "admin", "password": "test-account", "remember": True,
            "continue_case_id": case_id,
        })
        assert response.status_code == 200 and response.json()["continued_case_id"] == case_id
        assert auth.verify(response.json()["access_token"]) == ADMIN_USER
        record = store.get("u_dev-admin", case_id)
        assert record["documents"] == [] and "pending_question" not in record
        assert [row["provider"] for row in store.messages(case_id)] == ["photo", "recognition"]
        assert (tmp_path / "images" / case_id / (image_id + ".jpg")).read_bytes() == b"photo-bytes"
        assert store.get(owner, case_id) is None
        # 清理另一个旧临时记录不会删除已接续到管理员账户的记录。
        store.save(owner, {"id": "temporary"})
        assert client.post("/api/guest/end", json={}).status_code == 204
        assert store.get(owner, "temporary") is None
        assert store.get("u_dev-admin", case_id) is not None
