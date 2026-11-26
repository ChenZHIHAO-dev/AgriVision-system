"""Authenticate the single configured administrator without an account database."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from threading import RLock

ACCOUNT_PROVIDER = "configured-admin"
ADMIN_USER = {"id": "dev-admin", "username": "admin", "name": "Admin", "role": "admin"}
PBKDF2_ITERATIONS = 600_000
HASH_PREFIX = f"pbkdf2_sha256:{PBKDF2_ITERATIONS}"
ADMIN_HASH_FORMAT = re.compile(
    rf"{re.escape(HASH_PREFIX)}:([0-9a-f]{{32}}):([0-9a-f]{{64}})"
)


def _password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)


def hash_admin_password(password: str) -> str:
    if not 12 <= len(password) <= 64:
        raise ValueError("管理员密码长度需为 12–64 个字符")
    salt = secrets.token_bytes(16)
    return f"{HASH_PREFIX}:{salt.hex()}:{_password_digest(password, salt).hex()}"


class AuthManager:
    def __init__(self, admin_password_hash: str = ""):
        self.lock = RLock()
        self.sessions = {}
        self.signing_key = secrets.token_bytes(32)
        match = ADMIN_HASH_FORMAT.fullmatch(admin_password_hash.strip())
        self.password_hash = tuple(bytes.fromhex(part) for part in match.groups()) if match else None

    def login(self, username, password, remember=False):
        if self.password_hash is None:
            raise RuntimeError("管理员登录尚未配置，请联系维护人员")
        salt, digest = self.password_hash
        # 无论用户名是否正确都执行同一次密码校验，避免暴露账号匹配时差。
        valid_password = hmac.compare_digest(digest, _password_digest(password, salt))
        if username.strip().lower() != ADMIN_USER["username"] or not valid_password:
            raise ValueError("账号或密码不正确，请重新输入")

        token = secrets.token_urlsafe(40)
        expires = time.time() + (7 * 86400 if remember else 8 * 3600)
        with self.lock:
            self.sessions = {key: deadline for key, deadline in self.sessions.items() if deadline > time.time()}
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = expires
        return {
            "user": dict(ADMIN_USER),
            "access_token": token,
            "expires_at": expires,
            "account_provider": ACCOUNT_PROVIDER,
        }

    def verify(self, token):
        with self.lock:
            key = hashlib.sha256(token.encode()).hexdigest()
            expires = self.sessions.get(key)
            if expires is None or expires <= time.time():
                self.sessions.pop(key, None)
                return None
            return dict(ADMIN_USER)

    def logout(self, token):
        with self.lock:
            self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)

    def guest_owner(self, client_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", client_id):
            return ""
        digest = hmac.new(
            self.signing_key, b"guest-owner:" + client_id.encode(), hashlib.sha256
        ).hexdigest()
        return "g_" + digest

    def image_token(self, owner, case_id, image_id, session_token):
        # 原生 image 组件不能附加 Authorization；短期、单图授权绑定登录会话。
        session_key = hashlib.sha256(session_token.encode()).hexdigest()
        content = json.dumps(
            [owner, case_id, image_id, int(time.time() + 900), session_key], separators=(",", ":")
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
            owner, stored_case, stored_image, expires, session_key = json.loads(
                base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
            )
            with self.lock:
                session_active = self.sessions.get(session_key, 0) > time.time()
            return (
                owner
                if session_active
                and owner == "u_" + ADMIN_USER["id"]
                and stored_case == case_id
                and stored_image == image_id
                and expires > time.time()
                else None
            )
        except (ValueError, TypeError, UnicodeError):
            return None
