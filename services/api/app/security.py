"""统一业务入口的容量限制；单进程内测部署不依赖额外 Redis。"""
from collections import defaultdict, deque
from contextlib import contextmanager
import math
import re
from threading import Lock
import time

from fastapi import HTTPException
from starlette.responses import JSONResponse


class RequestLimits:
    """按服务端身份计数，并立即拒绝超过容量的请求，避免无限排队。"""

    def __init__(self):
        self.lock = Lock()
        self.events = defaultdict(deque)
        self.active = defaultdict(int)

    def reserve(self, key, count, seconds):
        now = time.monotonic()
        with self.lock:
            # 删除已过期的键，避免大量不同 IP 长期占用内存。
            for old_key in list(self.events):
                queue = self.events[old_key]
                while queue and queue[0][0] <= now - queue[0][2]:
                    queue.popleft()
                if not queue:
                    del self.events[old_key]
            queue = self.events[key]
            if len(queue) >= count:
                retry = max(1, math.ceil(queue[0][0] + seconds - now))
                raise HTTPException(429, "操作较频繁，请稍后重试", headers={"Retry-After": str(retry)})
            ticket = (now, object(), seconds)
            queue.append(ticket)
            return ticket

    def discard(self, key, ticket):
        """登录成功不计入失败额度；正在校验的请求仍占位，防止并发绕过。"""
        with self.lock:
            queue = self.events.get(key)
            if queue and ticket in queue:
                queue.remove(ticket)
            if queue is not None and not queue:
                self.events.pop(key, None)

    @contextmanager
    def slot(self, category, maximum):
        with self.lock:
            if self.active[category] >= maximum:
                raise HTTPException(429, "服务正在处理其他任务，请稍后重试", headers={"Retry-After": "2"})
            self.active[category] += 1
        try:
            yield
        finally:
            with self.lock:
                self.active[category] -= 1


def business_category(method, path):
    if method != "POST":
        return None
    if re.fullmatch(r"/api/cases/[^/]+/(messages|resume)", path):
        return "chat"
    if path in {"/api/cases", "/api/crop-recognition"} or re.fullmatch(
        r"/api/cases/[^/]+/(images|retry|attachments)", path
    ):
        return "recognition"
    return None


class RequestBodyLimit:
    """同时检查声明长度和实际流量，阻止分块上传绕过文件大小约束。"""

    def __init__(self, app, max_upload):
        self.app = app
        self.max_upload = max_upload

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        # multipart 允许少量表单开销；普通 JSON（含登录）无需大请求体。
        category = business_category(scope["method"], scope["path"])
        limit = self.max_upload + 64 * 1024 if category == "recognition" else 256 * 1024
        headers = dict(scope["headers"])
        declared = headers.get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            return await JSONResponse(status_code=413, content={"detail": "请求内容过大，请缩小文件后重试"})(scope, receive, send)
        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    raise HTTPException(413, "请求内容过大，请缩小文件后重试")
            return message

        await self.app(scope, limited_receive, send)
