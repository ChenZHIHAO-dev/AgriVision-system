import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = RLock()
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS cases_owner ON cases(owner, updated_at);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
            """)

    @contextmanager
    def connection(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=20)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            try:
                yield db
                db.commit()
            finally:
                db.close()

    def save(self, owner, case):
        with self.connection() as db:
            db.execute(
                "INSERT INTO cases VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,payload=excluded.payload WHERE cases.owner=excluded.owner",
                (case["id"], owner, case["created_at"], case["updated_at"], json.dumps(case, ensure_ascii=False)),
            )

    def get(self, owner, case_id):
        with self.connection() as db:
            row = db.execute("SELECT payload FROM cases WHERE id=? AND owner=?", (case_id, owner)).fetchone()
        return json.loads(row["payload"]) if row else None

    def list(self, owner, limit=100):
        with self.connection() as db:
            rows = db.execute("SELECT payload FROM cases WHERE owner=? ORDER BY updated_at DESC LIMIT ?", (owner, limit)).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def add_message(self, case_id, message):
        with self.connection() as db:
            db.execute("INSERT INTO messages(case_id,payload) VALUES(?,?)", (case_id, json.dumps(message, ensure_ascii=False)))

    def add_exchange(self, case_id, user, assistant):
        with self.connection() as db:
            db.executemany("INSERT INTO messages(case_id,payload) VALUES(?,?)", [(case_id, json.dumps(message, ensure_ascii=False)) for message in (user, assistant)])

    def messages(self, case_id):
        with self.connection() as db:
            rows = db.execute("SELECT payload FROM messages WHERE case_id=? ORDER BY id", (case_id,)).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def delete(self, owner, case_id):
        with self.connection() as db:
            db.execute("DELETE FROM cases WHERE id=? AND owner=?", (case_id, owner))
