"""Development account provider; no account database is created."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from threading import RLock


class AuthManager:
    def __init__(self):
        self.lock = RLock()
        self.users = {}
        self.sessions = {}
        self.signing_key = secrets.token_bytes(32)
        self._add("dev-admin", "admin", "Admin", "admin", "admin123")

    def _add(self, user_id, username, name, role, password):
        salt = secrets.token_hex(16)
        self.users[username] = {
            "id": user_id,
            "username": username,
            "name": name,
            "role": role,
            "salt": salt,
            "digest": self._digest(password, salt),
        }

    @staticmethod
    def _digest(password, salt):
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 180_000
        ).hex()

    @staticmethod
    def public(user):
        return {key: user[key] for key in ("id", "username", "name", "role")}

    def register(self, name, username, password):
        username = username.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,23}", username):
            raise ValueError("账号需为 3–24 位字母、数字或下划线，以字母开头")
        if not 1 <= len(name.strip()) <= 20:
            raise ValueError("请填写 1–20 字的称呼")
        if not 6 <= len(password) <= 64:
            raise ValueError("密码长度需为 6–64 位")
        with self.lock:
            if username in self.users:
                raise ValueError("这个账号已被使用，换一个试试")
            self._add(secrets.token_hex(16), username, name.strip(), "member", password)
        return self.login(username, password, False)

    def login(self, username, password, remember=False):
        username = username.strip().lower()
        with self.lock:
            user = self.users.get(username)
            if not user or not hmac.compare_digest(
                user["digest"], self._digest(password, user["salt"])
            ):
                raise ValueError("账号或密码不正确，请重新输入")
            token = secrets.token_urlsafe(40)
            expires = time.time() + (7 * 86400 if remember else 8 * 3600)
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = {
                "username": username,
                "expires": expires,
            }
            return {
                "user": self.public(user),
                "access_token": token,
                "expires_at": expires,
                "account_provider": "development-memory",
            }

    def verify(self, token):
        with self.lock:
            key = hashlib.sha256(token.encode()).hexdigest()
            session = self.sessions.get(key)
            if not session or session["expires"] <= time.time():
                self.sessions.pop(key, None)
                return None
            return self.public(self.users[session["username"]])

    def logout(self, token):
        with self.lock:
            self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)

    def image_token(self, owner, case_id, image_id):
        content = json.dumps(
            [owner, case_id, image_id, int(time.time() + 900)], separators=(",", ":")
        ).encode()
        body = base64.urlsafe_b64encode(content).decode().rstrip("=")
        signature = hmac.new(
            self.signing_key, body.encode(), hashlib.sha256
        ).hexdigest()
        return body + "." + signature

    def image_owner(self, token, case_id, image_id):
        try:
            body, signature = token.split(".")
            expected = hmac.new(
                self.signing_key, body.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return None
            owner, stored_case, stored_image, expires = json.loads(
                base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
            )
            return (
                owner
                if stored_case == case_id
                and stored_image == image_id
                and expires > time.time()
                else None
            )
        except (ValueError, TypeError, UnicodeError):
            return None
