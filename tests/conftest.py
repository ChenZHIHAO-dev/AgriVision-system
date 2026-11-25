import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT))



@pytest.fixture(scope="session")
def admin_hash():
    from app.auth import hash_admin_password

    return hash_admin_password("test-account")


@pytest.fixture
def account_headers():
    def login(client):
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "test-account"},
        )
        assert response.status_code == 200
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    return login
