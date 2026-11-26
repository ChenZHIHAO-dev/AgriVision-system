"""单管理员会话存储：记住登录进入现有 SQLite，普通登录仅存在当前进程。

不保存原始令牌或管理员密码。密码配置更换时，事务内清空会话并轮换图片
签名密钥；旧 AuthManager 每次使用时都核对代际，不能重新写回旧配置。
"""

import secrets
import time

from .store import Store


class SessionStore:
    storage_name = "sqlite-remember"

    def __init__(self, database: Store, credential_fingerprint: str):
        self.database = database
        self.fingerprint = credential_fingerprint
        self.temporary: dict[str, float] = {}
        with database.connection() as db:
            # IMMEDIATE 让初始化/配置轮换成为一次原子操作，也防止两个启动相互覆盖。
            db.execute("BEGIN IMMEDIATE")
            db.execute("""
                CREATE TABLE IF NOT EXISTS auth_state (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    credential_fingerprint TEXT NOT NULL,
                    signing_key BLOB NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_digest TEXT PRIMARY KEY,
                    expires_at REAL NOT NULL
                )
            """)
            state = db.execute("SELECT * FROM auth_state WHERE id=1").fetchone()
            if state is None or state["credential_fingerprint"] != self.fingerprint:
                self.signing_key = secrets.token_bytes(32)
                db.execute("DELETE FROM auth_sessions")
                db.execute("""
                    INSERT INTO auth_state VALUES(1,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                        credential_fingerprint=excluded.credential_fingerprint,
                        signing_key=excluded.signing_key
                """, (self.fingerprint, self.signing_key))
            else:
                self.signing_key = bytes(state["signing_key"])
            db.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (time.time(),))

    def _current(self, db) -> bool:
        state = db.execute("SELECT * FROM auth_state WHERE id=1").fetchone()
        # 同时比较随机代际密钥：密码从 A 改 B 再改回 A，不能复活旧进程的临时会话。
        return bool(
            state
            and state["credential_fingerprint"] == self.fingerprint
            and state["signing_key"] == self.signing_key
        )

    def issue(self, token_digest: str, expires_at: float, *, remember: bool):
        with self.database.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if not self._current(db):
                raise RuntimeError("登录配置已更新，请重新加载服务后登录")
            now = time.time()
            db.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (now,))
            self.temporary = {key: expiry for key, expiry in self.temporary.items() if expiry > now}
            if remember:
                db.execute("INSERT INTO auth_sessions VALUES(?,?)", (token_digest, expires_at))
            else:
                self.temporary[token_digest] = expires_at

    def active(self, token_digest: str) -> bool:
        with self.database.connection() as db:
            if not self._current(db):
                self.temporary.clear()
                return False
            now = time.time()
            expires = self.temporary.get(token_digest)
            if expires is not None:
                if expires > now:
                    return True
                self.temporary.pop(token_digest)
            row = db.execute(
                "SELECT expires_at FROM auth_sessions WHERE token_digest=?", (token_digest,)
            ).fetchone()
            if row and row["expires_at"] > now:
                return True
            if row:
                db.execute("DELETE FROM auth_sessions WHERE token_digest=?", (token_digest,))
            return False

    def revoke(self, token_digest: str):
        with self.database.connection() as db:
            self.temporary.pop(token_digest, None)
            db.execute("DELETE FROM auth_sessions WHERE token_digest=?", (token_digest,))
