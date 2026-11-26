"""联网业务统一鉴权、资源隔离和容量限制；不调用任何外部模型。"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from threading import Event

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.application import create_app
from app.config import Settings
from app.security import RequestLimits

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def app(tmp_path, admin_hash):
    return create_app(Settings(root=ROOT, runtime=tmp_path, models=tmp_path / "models",
                               admin_password_hash=admin_hash))


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/cases"), ("GET", "/api/cases/unknown"),
    ("POST", "/api/knowledge"), ("DELETE", "/api/knowledge/wheat_stripe_rust"),
    ("GET", "/api/admin/status"), ("GET", "/api/cases/id/images/photo"),
    ("POST", "/api/cases"), ("POST", "/api/cases/demo"),
    ("POST", "/api/crop-recognition"), ("POST", "/api/consultations"),
    ("POST", "/api/cases/id/images"), ("POST", "/api/cases/id/retry"),
    ("POST", "/api/cases/id/context"), ("POST", "/api/cases/id/messages"),
    ("POST", "/api/cases/id/resume"), ("POST", "/api/cases/id/attachments"),
    ("DELETE", "/api/cases/id"), ("DELETE", "/api/cases/id/images/photo"),
    ("DELETE", "/api/cases/id/attachments/document"), ("POST", "/api/guest/end"),
])
def test_anonymous_business_request_is_rejected_before_parsing(app, method, path):
    with TestClient(app) as client:
        response = client.request(method, path, headers={"X-Client-ID": "u_dev-admin"},
                                  content=b"invalid request")
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.headers["cache-control"] == "private, no-store"


def test_bootstrap_and_cors_work_without_login(app):
    with TestClient(app) as client:
        for path in ("/api/health", "/api/meta"):
            assert client.get(path, headers={"Authorization": "Bearer expired"}).status_code == 200
        assert client.post("/api/auth/register", json={}).status_code == 403
        response = client.get("/api/cases", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 401
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        preflight = client.options("/api/cases", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization",
        })
        assert preflight.status_code == 200


def test_image_grant_is_single_image_and_bound_to_session(app, account_headers):
    photo = BytesIO()
    Image.new("RGB", (320, 320), "#507c40").save(photo, "JPEG")
    with TestClient(app) as client:
        session = account_headers(client)
        record = client.post("/api/cases", headers=session, data={"crop": "wheat"},
                             files={"file": ("photo.jpg", photo.getvalue())}).json()
        image = record["images"][0]
        assert record["persistence"] == "account"
        image_response = client.get(image["url"])
        assert image_response.status_code == 200
        assert image_response.headers["cache-control"] == "private, no-store"
        assert client.get(image["url"].split("?")[0], headers=session).status_code == 200
        grant = image["url"].split("access_token=")[1]
        assert client.get("/api/cases?access_token=" + grant).status_code == 401
        assert client.delete(image["url"]).status_code == 401
        assert client.get(image["url"].replace(image["id"], "other")).status_code == 401
        assert client.get("/api/cases/" + record["id"],
                          headers={"X-Client-ID": "u_dev-admin"}).status_code == 401
        # X-Client-ID 无法覆盖服务端账户归属。
        assert client.get("/api/cases/" + record["id"],
                          headers={**session, "X-Client-ID": "forged-other"}).status_code == 200
        another = account_headers(client)
        assert client.post("/api/auth/logout", headers=session).status_code == 204
        assert client.get(image["url"]).status_code == 401
        fresh = client.get("/api/cases/" + record["id"], headers=another).json()
        assert client.get(fresh["images"][0]["url"]).status_code == 200


def test_failed_login_limit_cannot_be_bypassed_by_forwarded_ip(app, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("app.security.time.monotonic", lambda: clock[0])
    with TestClient(app) as client:
        for index in range(5):
            response = client.post("/api/auth/login",
                                   headers={"X-Forwarded-For": str(index)},
                                   json={"username": "admin", "password": "incorrect"})
            assert response.status_code == 401
        denied = client.post("/api/auth/login",
                             json={"username": "admin", "password": "test-account"})
        assert denied.status_code == 429 and int(denied.headers["retry-after"]) > 0
        clock[0] += 301
        for _ in range(6):
            success = client.post("/api/auth/login", json={
                "username": "admin", "password": "test-account",
            })
            assert success.status_code == 200
            assert success.headers["cache-control"] == "private, no-store"


def test_daily_chat_limit_is_shared_across_sessions_and_cases(tmp_path, admin_hash, account_headers):
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path / "models",
                        admin_password_hash=admin_hash, chat_per_day=1)
    with TestClient(create_app(settings)) as client:
        first = account_headers(client)
        record = client.post("/api/consultations", headers=first, json={}).json()
        path = "/api/cases/" + record["id"] + "/messages"
        assert client.post(path, headers=first, json={"text": "怎样拍清楚叶片？"}).status_code == 201
        second = account_headers(client)
        denied = client.post(path, headers=second, json={"text": "怎样拍清楚叶片？"})
        assert denied.status_code == 429


def test_chat_concurrency_rejects_instead_of_queuing(tmp_path, admin_hash, account_headers, monkeypatch):
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path / "models",
                        admin_password_hash=admin_hash, chat_concurrency=1)
    app = create_app(settings)
    entered, finish = Event(), Event()

    async def delayed(*args, **kwargs):
        entered.set()
        while not finish.is_set():
            await asyncio.sleep(.01)
        return {"text": "记录叶片症状", "provider": "knowledge", "sources": [], "products": []}

    monkeypatch.setattr(app.state.chat, "answer", delayed)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        headers = account_headers(client)
        records = [client.post("/api/consultations", headers=headers, json={}).json() for _ in range(2)]
        paths = ["/api/cases/" + row["id"] + "/messages" for row in records]
        running = pool.submit(client.post, paths[0], headers=headers, json={"text": "叶片有斑点"})
        try:
            assert entered.wait(5)
            assert client.post(paths[1], headers=headers, json={"text": "叶片有斑点"}).status_code == 429
        finally:
            finish.set()
        assert running.result(timeout=5).status_code == 201
        assert client.post(paths[1], headers=headers, json={"text": "叶片有斑点"}).status_code == 201


def test_body_limit_handles_chunked_upload_and_releases_slot(app, account_headers):
    with TestClient(app) as client:
        headers = account_headers(client)
        oversized = client.post("/api/cases", headers=headers, content=b"x" * (9 * 1024 * 1024))
        assert oversized.status_code == 413
        # 无 Content-Length 的流式 JSON 也受限。
        chunked = client.post("/api/consultations",
                              headers={**headers, "Content-Type": "application/json"},
                              content=iter([b'{"note":"', b"x" * (300 * 1024), b'"}']))
        assert chunked.status_code == 413
        assert client.post("/api/consultations", headers=headers, json={}).status_code == 201


def test_capacity_slot_is_released_on_exception():
    limits = RequestLimits()
    with pytest.raises(RuntimeError):
        with limits.slot("recognition", 1):
            raise RuntimeError("simulated")
    with limits.slot("recognition", 1):
        assert limits.active["recognition"] == 1

def test_build_commit_is_available_in_public_bootstrap(tmp_path):
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path / "models", build_commit="123abc456")
    with TestClient(create_app(settings)) as client:
        for path in ("/api/health", "/api/meta"):
            result = client.get(path).json()
            assert result["build_commit"] == "123abc456"
            assert result["version"] == client.app.version


def test_recognition_limit_covers_crop_upload_and_retry(tmp_path, admin_hash, account_headers):
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path / "models",
                        admin_password_hash=admin_hash, recognition_per_minute=1)
    with TestClient(create_app(settings)) as client:
        headers = account_headers(client)
        assert client.post("/api/crop-recognition", headers=headers,
                           files={"file": ("bad.jpg", b"invalid")}).status_code == 422
        # 上传和重试共用资源额度，不能通过切换入口绕过。
        assert client.post("/api/cases/unknown/retry", headers=headers).status_code == 429


def test_authenticated_viewer_cannot_read_another_owner_record(app, account_headers):
    with TestClient(app) as client:
        headers = account_headers(client)
        own = client.post("/api/consultations", headers=headers, json={}).json()
        client.post("/api/cases/" + own["id"] + "/messages",
                    headers=headers, json={"text": "怎样拍清楚叶片？"})
        foreign = {**own, "id": "a" * 32}
        app.state.store.save("u_other-account", foreign)
        assert client.get("/api/cases/" + foreign["id"], headers=headers).status_code == 404
        assert client.delete("/api/cases/" + foreign["id"], headers=headers).status_code == 404
        assert [item["id"] for item in client.get("/api/cases", headers=headers).json()["items"]] == [own["id"]]


def test_request_limits_are_isolated_between_application_instances(tmp_path, admin_hash, account_headers):
    # 中间件模块可复用，但不同应用不能因同一账号ID而共享内存中的限流额度。
    first_settings = Settings(root=ROOT, runtime=tmp_path / "first", models=tmp_path / "models",
                              admin_password_hash=admin_hash, chat_per_day=1)
    second_settings = replace(first_settings, runtime=tmp_path / "second")
    with TestClient(create_app(first_settings)) as first, TestClient(create_app(second_settings)) as second:
        for client in (first, second):
            headers = account_headers(client)
            record = client.post("/api/consultations", headers=headers, json={}).json()
            path = "/api/cases/" + record["id"] + "/messages"
            assert client.post(path, headers=headers, json={"text": "怎样拍清楚叶片？"}).status_code == 201
            assert client.post(path, headers=headers, json={"text": "怎样拍清楚叶片？"}).status_code == 429


def test_public_reference_cards_do_not_require_identity(app):
    with TestClient(app) as client:
        for headers in ({}, {"Authorization": "Bearer expired"}):
            listing = client.get("/api/knowledge", params={"q": "锈病"}, headers=headers)
            assert listing.status_code == 200 and listing.json()["items"]
            detail = client.get("/api/knowledge/wheat_leaf_rust", headers=headers)
            assert detail.status_code == 200 and detail.json()["id"] == "wheat_leaf_rust"
            assert client.get("/api/knowledge/not-a-card", headers=headers).status_code == 404
        # 公共资料不包含用户记录，图片签名也不能取得个人历史。
        assert client.get("/api/knowledge/wheat_leaf_rust/private").status_code == 401
        assert client.get("/api/cases").status_code == 401
