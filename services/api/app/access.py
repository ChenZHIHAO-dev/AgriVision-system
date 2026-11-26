"""HTTP 访问边界：解析身份、注入记录归属，并应用统一业务额度。

AuthManager 负责凭证与签名，security 负责计数和并发控制；本模块只协调
请求入口，不访问数据库或调用识别/对话模型。application 仅负责注册它。
"""

import re

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from .auth import AuthManager
from .config import Settings
from .security import RequestLimits, business_category


# 默认所有 /api/ 业务都需要身份；只显式放行启动信息和登录/禁用注册入口。
PUBLIC_ENDPOINTS = frozenset({
    ("GET", "/api/health"), ("GET", "/api/meta"),
    ("POST", "/api/auth/login"), ("POST", "/api/auth/register"),
})


class AccountScopeMiddleware(BaseHTTPMiddleware):
    """每个应用持有自己的限流状态，多个应用实例不会共享用户额度。"""

    def __init__(self, app, *, auth: AuthManager, settings: Settings):
        super().__init__(app)
        self.auth = auth
        self.settings = settings
        self.limits = RequestLimits()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path, method = request.url.path, request.method
        if not path.startswith("/api/") or method == "OPTIONS":
            return await call_next(request)
        async def business_response():
            response = await call_next(request)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        public = (method, path) in PUBLIC_ENDPOINTS
        bearer = request.headers.get("authorization", "")
        token = bearer[7:] if bearer.startswith("Bearer ") else ""
        viewer = self.auth.verify(token) if token else None
        # 图片组件可使用绑定登录会话的单图签名，仅允许读取这张图片。
        image_match = re.fullmatch(r"/api/cases/([^/]+)/images/([^/]+)", path)
        image_owner = None
        if method == "GET" and image_match:
            image_owner = self.auth.image_owner(
                request.query_params.get("access_token", ""), *image_match.groups()
            )
        # 登录和启动元信息允许失效的旧 token；全部业务入口默认拒绝匿名访问。
        if not public and viewer is None and image_owner is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "登录已过期，请重新登录" if token else "请先登录后使用服务"},
                headers={"WWW-Authenticate": "Bearer", "Cache-Control": "private, no-store"},
            )
        scope = "u_" + viewer["id"] if viewer else image_owner or ""
        request.state.viewer = viewer
        request.state.owner = scope
        request.state.token = token
        # 客户端传来的 owner 不可信；后续路由只接收这里重写的服务端归属。
        headers = [(key, value) for key, value in request.scope["headers"] if key != b"x-client-id"]
        if scope:
            headers.append((b"x-client-id", scope.encode()))
        request.scope["headers"] = headers
        try:
            if method == "POST" and path == "/api/auth/login":
                # 只信任 ASGI 服务器给出的地址，不接受客户端伪造 X-Forwarded-For。
                address = request.client.host if request.client else "unknown"
                key = ("login", address)
                with self.limits.slot("login", 2):
                    ticket = self.limits.reserve(key, self.settings.login_attempts, self.settings.login_window_seconds)
                    response = await business_response()
                    if response.status_code < 400:
                        self.limits.discard(key, ticket)
                    return response
            category = business_category(method, path)
            if category:
                maximum = self.settings.chat_concurrency if category == "chat" else self.settings.recognition_concurrency
                with self.limits.slot(category, maximum):
                    if category == "chat":
                        self.limits.reserve(("chat-hour", scope), self.settings.chat_per_hour, 3600)
                        self.limits.reserve(("chat-day", scope), self.settings.chat_per_day, 86400)
                    else:
                        self.limits.reserve(("recognition", scope), self.settings.recognition_per_minute, 60)
                    return await business_response()
            return await business_response()
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.detail},
                headers={**(exc.headers or {}), "Cache-Control": "private, no-store"},
            )


def require_account(request: Request):
    """需要账户身份的路由依赖；单图签名不会被视为完整登录会话。"""
    if not request.state.viewer:
        raise HTTPException(
            401, "请先登录后使用服务", headers={"WWW-Authenticate": "Bearer"}
        )
