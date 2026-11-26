"""认证/账户 HTTP 接口。

AuthManager 校验凭证，CaseRepository 管理记录；本模块仅协调接口、登录接续
和状态码。模型状态通过只读函数注入，不依赖模型实现或启动外部服务。
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .auth import ACCOUNT_PROVIDER, AuthManager
from .repository import CaseRepository
from .schemas import GuestEndRequest, LoginRequest


def create_account_router(
    *,
    auth: AuthManager,
    store: CaseRepository,
    mutation: Callable[[str], AbstractContextManager],
    version: str,
    model_status: Callable[[], Any],
    deepseek_configured: Callable[[], bool],
) -> APIRouter:
    router = APIRouter(prefix="/api")

    def finish_sign_in(request, result, continue_case_id):
        guest_owner = request.state.owner
        if continue_case_id:
            try:
                with mutation(continue_case_id):
                    account_owner = "u_" + result["user"]["id"]
                    if not store.continue_case(guest_owner, account_owner, continue_case_id):
                        raise HTTPException(404, "这条临时识别记录已失效，请重新拍照或上传")
            except Exception:
                # 接续失败时撤销刚创建的会话，不能留下调用者不知道的有效令牌。
                auth.logout(result["access_token"])
                raise
            result["continued_case_id"] = continue_case_id
        elif store.temporary_owner(guest_owner):
            store.clear_guest(guest_owner)
        return result

    @router.post("/auth/login")
    def login(request: Request, body: LoginRequest):
        try:
            result = auth.login(body.username, body.password, body.remember)
        except ValueError as exc:
            raise HTTPException(401, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        return finish_sign_in(request, result, body.continue_case_id)

    @router.post("/auth/register")
    def register():
        raise HTTPException(403, "当前仅开放管理员登录")

    @router.get("/auth/me")
    def account(request: Request):
        if not request.state.viewer:
            raise HTTPException(401, "请先登录")
        return {"user": request.state.viewer, "account_provider": ACCOUNT_PROVIDER}

    @router.post("/auth/logout", status_code=204)
    def logout(request: Request):
        auth.logout(request.state.token)

    @router.post("/guest/end", status_code=204)
    def end_guest(request: Request, body: GuestEndRequest):
        guest = (
            request.state.owner
            if request.state.owner.startswith("g_")
            else auth.guest_owner(body.client_id)
        )
        if guest:
            store.clear_guest(guest)

    @router.get("/admin/status")
    def admin_status(request: Request):
        if not request.state.viewer:
            raise HTTPException(401, "请先登录管理员账户")
        if request.state.viewer["role"] != "admin":
            raise HTTPException(403, "仅管理员可查看服务配置")
        return {
            "version": version,
            "models": model_status(),
            "deepseek_configured": deepseek_configured(),
            "account_provider": ACCOUNT_PROVIDER,
            "record_storage": "server",
            "business_access": "authenticated",
            "session_storage": auth.sessions.storage_name,
            "web_search_models": ["deepseek-flash"],
        }

    return router
