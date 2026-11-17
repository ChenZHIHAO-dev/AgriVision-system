"""Guest context lives in RAM; only authenticated account records reach SQLite."""

from copy import deepcopy
from threading import RLock
import time

from .store import Store


class CaseRepository:
    def __init__(self, path):
        self.persistent = Store(path)
        self.path = path
        self.lock = RLock()
        self.temporary = {}
        self.image_bytes = {}
        self.ttl = 1800

    @staticmethod
    def temporary_owner(owner):
        return owner.startswith("g_")

    def _drop(self, case_id):
        self.temporary.pop(case_id, None)
        for key in [key for key in self.image_bytes if key[0] == case_id]:
            self.image_bytes.pop(key, None)

    def _prune(self):
        now = time.time()
        for case_id in [
            key for key, value in self.temporary.items() if value["expires"] <= now
        ]:
            self._drop(case_id)
        for key in [
            key for key, value in self.image_bytes.items() if value["expires"] <= now
        ]:
            self.image_bytes.pop(key, None)

    def save(self, owner, case):
        if not self.temporary_owner(owner):
            return self.persistent.save(owner, case)
        with self.lock:
            self._prune()
            if case["id"] not in self.temporary:
                for old in [
                    key
                    for key, value in self.temporary.items()
                    if value["owner"] == owner
                ]:
                    self._drop(old)
            old = self.temporary.get(case["id"], {})
            self.temporary[case["id"]] = {
                "owner": owner,
                "case": deepcopy(case),
                "messages": old.get("messages", []),
                "expires": time.time() + self.ttl,
            }

            self._touch_images(case["id"])

    def _touch_images(self, case_id):
        for (stored_case, _), value in self.image_bytes.items():
            if stored_case == case_id:
                value["expires"] = time.time() + self.ttl

    def get(self, owner, case_id):
        if not self.temporary_owner(owner):
            return self.persistent.get(owner, case_id)
        with self.lock:
            self._prune()
            value = self.temporary.get(case_id)
            if not value or value["owner"] != owner:
                return None
            value["expires"] = time.time() + self.ttl
            self._touch_images(case_id)
            return deepcopy(value["case"])

    def list(self, owner, limit=100):
        return [] if self.temporary_owner(owner) else self.persistent.list(owner, limit)

    def owner_of(self, case_id):
        with self.lock:
            if case_id in self.temporary:
                return self.temporary[case_id]["owner"]
        with self.persistent.connection() as db:
            row = db.execute(
                "SELECT owner FROM cases WHERE id=?", (case_id,)
            ).fetchone()
            return row["owner"] if row else None

    def clear_guest(self, owner):
        with self.lock:
            for case_id in [
                key for key, value in self.temporary.items() if value["owner"] == owner
            ]:
                self._drop(case_id)

    def messages(self, case_id):
        with self.lock:
            self._prune()
            if case_id in self.temporary:
                return deepcopy(self.temporary[case_id]["messages"])
        return self.persistent.messages(case_id)

    def add_message(self, case_id, message):
        with self.lock:
            if case_id in self.temporary:
                self.temporary[case_id]["messages"].append(deepcopy(message))
                return
        if self.owner_of(case_id) is not None:
            self.persistent.add_message(case_id, message)

    def add_exchange(self, case_id, user, assistant):
        with self.lock:
            if case_id in self.temporary:
                self.temporary[case_id]["messages"].extend(deepcopy([user, assistant]))
                return
        if self.owner_of(case_id) is not None:
            self.persistent.add_exchange(case_id, user, assistant)

    def delete(self, owner, case_id):
        if not self.temporary_owner(owner):
            return self.persistent.delete(owner, case_id)
        with self.lock:
            if self.temporary.get(case_id, {}).get("owner") == owner:
                self._drop(case_id)

    def put_image(self, owner, case_id, image_id, content):
        with self.lock:
            self.image_bytes[(case_id, image_id)] = {
                "owner": owner,
                "content": content,
                "expires": time.time() + self.ttl,
            }

    def remove_image(self, case_id, image_id):
        with self.lock:
            self.image_bytes.pop((case_id, image_id), None)

    def get_image(self, owner, case_id, image_id):
        with self.lock:
            self._prune()
            value = self.image_bytes.get((case_id, image_id))
            return value["content"] if value and value["owner"] == owner else None
