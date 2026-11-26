import re
import uuid
from contextlib import contextmanager
from io import BytesIO
from threading import Lock

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .attachments import extract_document
from .auth import ACCOUNT_PROVIDER, AuthManager
from .case_views import now, seed_photo_transcript, serialize_case
from .chat import Chat
from .config import Settings
from .context import STAGES, fill_explicit_context, is_general_question
from .conversation_policy import apply_context_choices, conversation_scope
from .crop_recognition import CropRecognizer
from .evidence import aggregate_images
from .imaging import prepare_image
from .intake import optional_context_response
from .knowledge import CROP_NAMES, Knowledge, crop_scope_conflicts, query_crop_scope
from .models import ModelRegistry
from .recognition import recognition_state
from .repository import CaseRepository
from .schemas import (
    CaseUpdate,
    ConsultationRequest,
    Crop,
    CropRecognitionResponse,
    DemoRequest,
    GuestEndRequest,
    LoginRequest,
    MessageRequest,
    ResumeRequest,
)


def append_prediction_version(case, image_id, prediction, *, trigger=None):
    version = {
        **prediction,
        "image_id": image_id,
        "created_at": now(),
        "crop": case["crop"],
        "stage": case["stage"],
    }
    if trigger is not None:
        version["trigger"] = trigger
    case["versions"].append(version)


def create_app(settings=None):
    settings = settings or Settings.from_env()
    store = CaseRepository(settings.runtime / "agrivision.sqlite3")
    auth = AuthManager(settings.admin_password_hash)
    knowledge = Knowledge(settings.root)
    registry = ModelRegistry(settings, knowledge)
    crop_recognizer = CropRecognizer(settings)
    chat = Chat(settings, knowledge)
    case_locks = {}
    lock_guard = Lock()

    app = FastAPI(title="AgriVision API", version="1.4.0-beta.1")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors),
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Client-ID", "Authorization"],
    )
    app.state.registry = registry
    app.state.crop_recognizer = crop_recognizer
    app.state.store = store
    app.state.chat = chat
    app.state.auth = auth

    @app.middleware("http")
    async def account_scope(request: Request, call_next):
        bearer = request.headers.get("authorization", "")
        token = bearer[7:] if bearer.startswith("Bearer ") else ""
        viewer = auth.verify(token) if token else None
        if token and viewer is None:
            return JSONResponse(
                status_code=401, content={"detail": "登录已过期，请重新登录"}
            )
        raw = request.headers.get("x-client-id", "")
        scope = "u_" + viewer["id"] if viewer else auth.guest_owner(raw)
        request.state.viewer = viewer
        request.state.owner = scope
        request.state.token = token
        headers = [
            (key, value)
            for key, value in request.scope["headers"]
            if key != b"x-client-id"
        ]
        if scope:
            headers.append((b"x-client-id", scope.encode()))
        request.scope["headers"] = headers
        return await call_next(request)

    def require_account(request: Request):
        if not request.state.viewer:
            raise HTTPException(
                401, "请先登录后向 AI 提问", headers={"WWW-Authenticate": "Bearer"}
            )

    def finish_sign_in(request, result, continue_case_id):
        guest_owner = request.state.owner
        if continue_case_id:
            try:
                with mutation(continue_case_id):
                    account_owner = "u_" + result["user"]["id"]
                    if not store.continue_case(guest_owner, account_owner, continue_case_id):
                        raise HTTPException(404, "这条临时识别记录已失效，请重新拍照或上传")
            except Exception:
                auth.logout(result["access_token"])
                raise
            result["continued_case_id"] = continue_case_id
        elif store.temporary_owner(guest_owner):
            store.clear_guest(guest_owner)
        return result

    @app.post("/api/auth/login")
    def login(request: Request, body: LoginRequest):
        try:
            result = auth.login(body.username, body.password, body.remember)
        except ValueError as exc:
            raise HTTPException(401, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        return finish_sign_in(request, result, body.continue_case_id)

    @app.post("/api/auth/register")
    def register():
        raise HTTPException(403, "当前仅开放管理员登录")

    @app.get("/api/auth/me")
    def account(request: Request):
        if not request.state.viewer:
            raise HTTPException(401, "请先登录")
        return {"user": request.state.viewer, "account_provider": ACCOUNT_PROVIDER}

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request):
        auth.logout(request.state.token)

    @app.post("/api/guest/end", status_code=204)
    def end_guest(request: Request, body: GuestEndRequest):
        guest = (
            request.state.owner
            if request.state.owner.startswith("g_")
            else auth.guest_owner(body.client_id)
        )
        if guest:
            store.clear_guest(guest)

    @app.get("/api/admin/status")
    def admin_status(request: Request):
        if not request.state.viewer:
            raise HTTPException(401, "请先登录管理员账户")
        if request.state.viewer["role"] != "admin":
            raise HTTPException(403, "仅管理员可查看服务配置")
        return {
            "version": app.version,
            "models": registry.status(),
            "deepseek_configured": bool(settings.get_deepseek_key()),
            "account_provider": ACCOUNT_PROVIDER,
            "record_storage": "server",
            "guest_storage": "volatile-memory",
            "web_search_models": ["deepseek-flash"],
        }

    @contextmanager
    def mutation(case_id):
        with lock_guard:
            lock = case_locks.setdefault(case_id, Lock())
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "这条记录正在处理，请稍后重试")
        try:
            yield
        finally:
            lock.release()

    def owner(value):
        if not value or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", value):
            raise HTTPException(400, "缺少有效的本地会话标识")
        return value

    def get_case(client, case_id):
        case = store.get(owner(client), case_id)
        if case is None:
            raise HTTPException(404, "这条记录不存在")
        case.update(aggregate_images(case))
        return case

    def serialize(case):
        return serialize_case(case, store=store, auth=auth, knowledge=knowledge)

    def base_case(crop, location="", stage="不清楚", note=""):
        timestamp = now()
        return {
            "id": uuid.uuid4().hex,
            "crop": crop,
            "crop_name": CROP_NAMES.get(crop, "作物待补充"),
            "location": location,
            "stage": stage,
            "note": note,
            "variety": "",
            "created_at": timestamp,
            "updated_at": timestamp,
            "is_demo": False,
            "images": [],
            "documents": [],
            "versions": [],
            "status": "needs_model",
            "title": "图片已保存，识别模型准备中",
            "candidates": [],
            "disease_id": None,
            "model_version": None,
        }

    async def read_processed_photo(upload):
        try:
            content = await upload.read(settings.max_upload + 1)
        finally:
            await upload.close()
        if len(content) > settings.max_upload:
            raise HTTPException(413, "图片不能超过 8MB，请压缩后重试")
        try:
            return prepare_image(content)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    async def apply_upload(case, upload, client):
        normalized, quality = await read_processed_photo(upload)
        image_id = uuid.uuid4().hex
        folder = settings.runtime / "images" / case["id"]
        path = folder / (image_id + ".jpg")
        if store.temporary_owner(client):
            store.put_image(client, case["id"], image_id, normalized)
            model_input = BytesIO(normalized)
        else:
            folder.mkdir(parents=True, exist_ok=True)
            path.write_bytes(normalized)
            model_input = path
        case["images"].append(
            {
                "id": image_id,
                "quality": quality,
                "created_at": now(),
                "crop": case["crop"],
                "stage": case["stage"],
            }
        )
        if quality["issues"]:
            prediction = {
                "status": "needs_retake",
                "title": "需要一张更清晰的症状照片",
                "candidates": [],
                "disease_id": None,
                "model_version": None,
            }
        else:
            prediction = await run_in_threadpool(
                registry.predict, case["crop"], model_input
            )
        case.update(prediction)
        append_prediction_version(case, image_id, prediction)
        case.update(aggregate_images(case))
        case["updated_at"] = now()
        return case

    @app.get("/api/health")
    def health():
        return {"application": "agrivision", "status": "ok", "version": app.version}

    @app.get("/api/meta")
    def meta():
        return {
            "version": app.version,
            "models": registry.status(),
            "deepseek_configured": bool(settings.get_deepseek_key()),
            "knowledge_count": len(knowledge.cards),
            "crop_recognition": crop_recognizer.status(),
            "product_count": len([p for p in knowledge.products if p.approved]),
            "max_upload_mb": 8,
            "mode": "local-development",
            "chat_models": ["deepseek-flash", "deepseek-v4-pro"],
            "thinking_supported": True,
            "document_types": ["txt", "md", "pdf", "docx"],
            "stages": STAGES,
        }

    @app.get("/api/knowledge")
    def list_knowledge(q: str = "", crop: Crop | None = None):
        return {"items": knowledge.search(q[:200], crop)}

    @app.get("/api/knowledge/{card_id}")
    def knowledge_detail(card_id: str):
        card = knowledge.get(card_id)
        if card is None:
            raise HTTPException(404, "资料不存在")
        return card

    @app.get("/api/cases")
    def cases(x_client_id: str = Header(default="")):
        return {
            "items": [
                serialize(case)
                for case in store.list(owner(x_client_id))
                if case.get("images")
                or case.get("is_demo")
                or store.messages(case["id"])
            ]
        }

    @app.post("/api/cases/demo", status_code=201)
    def demo(body: DemoRequest, x_client_id: str = Header(default="")):
        client = owner(x_client_id)
        disease = {
            "wheat": "wheat_stripe_rust",
            "maize": "maize_southern_rust",
            "peanut": "peanut_leaf_spot",
        }[body.crop]
        card = knowledge.get(disease)
        case = base_case(
            body.crop,
            stage="演示阶段",
            note="此记录为功能演示，不是对用户照片的识别结果",
        )
        case.update(
            {
                "is_demo": True,
                "status": "demo",
                "title": card["title"] + " · 演示样例",
                "disease_id": disease,
            }
        )
        store.save(client, case)
        return serialize(case)

    @app.post("/api/crop-recognition", response_model=CropRecognitionResponse)
    async def identify_crop(file: UploadFile = File(...)):
        normalized, quality = await read_processed_photo(file)
        if quality["issues"]:
            return CropRecognitionResponse(status="needs_retake", quality_issues=quality["issues"])
        return await run_in_threadpool(crop_recognizer.predict, BytesIO(normalized))

    @app.post("/api/cases", status_code=201)
    async def create_case(
        file: UploadFile = File(...),
        crop: Crop = Form(...),
        location: str = Form(default="", max_length=120),
        stage: str = Form(default="不清楚", max_length=40),
        note: str = Form(default="", max_length=2000),
        x_client_id: str = Header(default=""),
    ):
        client = owner(x_client_id)
        case = await apply_upload(base_case(crop, location, stage, note), file, client)
        store.save(client, case)
        seed_photo_transcript(case, store=store, knowledge=knowledge)
        return serialize(case)

    @app.post(
        "/api/consultations", status_code=201, dependencies=[Depends(require_account)]
    )
    def consultation(body: ConsultationRequest, x_client_id: str = Header(default="")):
        client = owner(x_client_id)
        case = base_case(body.crop, body.location, body.stage)
        case.update(
            {
                "status": "awaiting_image",
                "title": CROP_NAMES.get(body.crop, "作物") + "种植问答",
                "variety": body.variety,
            }
        )
        store.save(client, case)
        return serialize(case)

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str, x_client_id: str = Header(default="")):
        return serialize(get_case(x_client_id, case_id))

    @app.post("/api/cases/{case_id}/context")
    def update_case(
        case_id: str, body: CaseUpdate, x_client_id: str = Header(default="")
    ):
        with mutation(case_id):
            case = get_case(x_client_id, case_id)
            if body.crop is not None:
                if case["images"] and case["crop"] != body.crop:
                    raise HTTPException(409, "更换照片对应作物时，请重新添加图片并识别")
                case["crop_name"] = CROP_NAMES[body.crop]
                if not case["images"]:
                    case["title"] = CROP_NAMES[body.crop] + "种植问答"
            fields = body.model_dump(exclude_none=True)
            if body.conversation_title is not None:
                fields["conversation_title"] = " ".join(body.conversation_title.split())
            apply_context_choices(case, fields)
            case["updated_at"] = now()
            store.save(x_client_id, case)
            return serialize(case)

    @app.post("/api/cases/{case_id}/images")
    async def supplement(
        case_id: str,
        file: UploadFile = File(...),
        crop: Crop | None = Form(default=None),
        stage: str | None = Form(default=None, max_length=40),
        variety: str | None = Form(default=None, max_length=80),
        x_client_id: str = Header(default=""),
    ):
        with mutation(case_id):
            case = get_case(x_client_id, case_id)
            if case["is_demo"]:
                raise HTTPException(409, "演示记录不接收照片。请新建一条识别记录")
            if len(case["images"]) >= 6:
                raise HTTPException(422, "每条识别记录最多保存 6 张照片")
            changed_crop = crop is not None and crop != case.get("crop")
            if changed_crop and case["images"]:
                raise HTTPException(
                    409, "一条识别记录只对应一种作物。识别其他作物时，请新建记录"
                )
            if crop is not None:
                case.update({"crop": crop, "crop_name": CROP_NAMES[crop]})
            if changed_crop:
                case["stage"] = "不清楚"
            # An upload's placeholder must not erase a stage already supplied in chat.
            if stage is not None and (
                stage not in ("", "不清楚") or case["stage"] in ("", "不清楚")
            ):
                case["stage"] = stage
            if variety is not None:
                case["variety"] = variety
            if not case.get("crop"):
                raise HTTPException(422, "请先选择照片中的作物")
            case = await apply_upload(case, file, owner(x_client_id))
            store.save(x_client_id, case)
            return serialize(case)

    @app.delete("/api/cases/{case_id}/images/{image_id}")
    def remove_unsent_image(
        case_id: str, image_id: str, x_client_id: str = Header(default="")
    ):
        with mutation(case_id):
            case = get_case(x_client_id, case_id)
            if not any(image["id"] == image_id for image in case["images"]):
                raise HTTPException(404, "照片不存在")
            for message in store.messages(case_id):
                references = message.get("attachments", []) + (
                    message.get("recognition") or {}
                ).get("image_results", [])
                if any(
                    item.get("id", item.get("image_id")) == image_id
                    for item in references
                ):
                    raise HTTPException(
                        409, "这张照片已用于对话。要调整图片范围，请新建一条识别记录"
                    )
            case["images"] = [
                image for image in case["images"] if image["id"] != image_id
            ]
            case["versions"] = [
                version
                for version in case["versions"]
                if version.get("image_id") != image_id
            ]
            if store.temporary_owner(x_client_id):
                store.remove_image(case_id, image_id)
            else:
                (settings.runtime / "images" / case_id / (image_id + ".jpg")).unlink(
                    missing_ok=True
                )
            if case["images"]:
                case.update(aggregate_images(case))
            else:
                case.update(
                    status="awaiting_image",
                    title=CROP_NAMES.get(case["crop"], "作物") + "种植问答",
                    candidates=[],
                    disease_id=None,
                    model_version=None,
                    experimental=False,
                )
                case.pop("evidence", None)
            case["updated_at"] = now()
            store.save(x_client_id, case)
            return serialize(case)

    @app.post("/api/cases/{case_id}/retry")
    async def retry_recognition(case_id: str, x_client_id: str = Header(default="")):
        with mutation(case_id):
            case = get_case(x_client_id, case_id)
            if case["is_demo"] or not case["images"]:
                raise HTTPException(409, "请先添加真实症状照片")
            inputs = []
            for image in case["images"]:
                if image.get("quality", {}).get("issues"):
                    continue
                if store.temporary_owner(x_client_id):
                    content = store.get_image(x_client_id, case_id, image["id"])
                    if content is None:
                        raise HTTPException(410, "照片已过期，请重新上传")
                    model_input = BytesIO(content)
                else:
                    model_input = (
                        settings.runtime / "images" / case_id / (image["id"] + ".jpg")
                    )
                    if not model_input.is_file():
                        raise HTTPException(410, "原始照片已不可用，请重新上传")
                inputs.append((image, model_input))
            if not inputs:
                raise HTTPException(422, "现有照片均需要补拍，请上传更清晰的照片")
            for image, model_input in inputs:
                prediction = await run_in_threadpool(
                    registry.predict, case["crop"], model_input
                )
                append_prediction_version(case, image["id"], prediction, trigger="retry")
            case.update(aggregate_images(case))
            case["updated_at"] = now()
            store.save(x_client_id, case)
            return serialize(case)

    @app.post(
        "/api/cases/{case_id}/attachments",
        status_code=201,
        dependencies=[Depends(require_account)],
    )
    async def document(
        case_id: str,
        file: UploadFile = File(...),
        filename: str | None = Form(default=None, max_length=160),
        x_client_id: str = Header(default=""),
    ):
        with mutation(case_id):
            case = get_case(x_client_id, case_id)
            if len(case.get("documents", [])) >= 6:
                raise HTTPException(422, "每条对话最多添加 6 份资料")
            content = await file.read(settings.max_upload + 1)
            await file.close()
            try:
                item = extract_document(
                    filename or file.filename or "document", content
                )
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            item.update({"id": uuid.uuid4().hex, "created_at": now()})
            case.setdefault("documents", []).append(item)
            case["updated_at"] = now()
            store.save(x_client_id, case)
            return serialize(case)

    @app.delete(
        "/api/cases/{case_id}/attachments/{attachment_id}",
        status_code=204,
        dependencies=[Depends(require_account)],
    )
    def remove_document(
        case_id: str, attachment_id: str, x_client_id: str = Header(default="")
    ):
        with mutation(case_id):
            case = get_case(x_client_id, case_id)
            if not any(
                document["id"] == attachment_id
                for document in case.get("documents", [])
            ):
                raise HTTPException(404, "资料附件不存在")
            case["documents"] = [
                document
                for document in case["documents"]
                if document["id"] != attachment_id
            ]
            case["updated_at"] = now()
            store.save(x_client_id, case)

    @app.get("/api/cases/{case_id}/images/{image_id}")
    def image(case_id: str, image_id: str, access_token: str = ""):
        image_owner = auth.image_owner(access_token, case_id, image_id)
        if not image_owner:
            raise HTTPException(404, "图片链接已失效，请刷新记录")
        case = get_case(image_owner, case_id)
        if not any(img["id"] == image_id for img in case["images"]):
            raise HTTPException(404, "图片不存在")
        if store.temporary_owner(image_owner):
            content = store.get_image(image_owner, case_id, image_id)
            if content is None:
                raise HTTPException(404, "临时图片已过期，请重新上传")
            return Response(
                content,
                media_type="image/jpeg",
                headers={"Cache-Control": "private, no-store"},
            )
        return FileResponse(
            settings.runtime / "images" / case_id / (image_id + ".jpg"),
            media_type="image/jpeg",
            headers={"Cache-Control": "private, no-store"},
        )

    def validate_options(model, web_search):
        if web_search and (model or settings.deepseek_model) != "deepseek-flash":
            raise HTTPException(422, "联网检索请选择 DeepSeek Flash")

    def add_receipt(answer, case, text, image_ids, history):
        scope = conversation_scope(text, history)
        if scope is not None and scope != frozenset({case.get("crop")}):
            return
        if case.get("images") and (
            image_ids or re.search(r"识别|图片|照片|结果|病害", text)
        ):
            answer["recognition"] = recognition_state(case)

    @app.post("/api/cases/{case_id}/resume", dependencies=[Depends(require_account)])
    async def resume(
        case_id: str, body: ResumeRequest, x_client_id: str = Header(default="")
    ):
        with mutation(case_id):
            case = get_case(x_client_id, case_id)
            history = store.messages(case_id)
            completed = next(
                (
                    message
                    for message in reversed(history)
                    if message.get("resolved_question_id") == body.question_id
                ),
                None,
            )
            if completed:
                return completed
            pending = case.get("pending_question")
            if not pending or pending["id"] != body.question_id:
                raise HTTPException(409, "待回答问题已更新，请刷新当前对话")
            options = {
                key: getattr(body, key)
                if getattr(body, key) is not None
                else pending.get(key)
                for key in ("model", "thinking", "web_search")
            }
            validate_options(options["model"], options["web_search"])
            answer = await chat.answer(case, pending["text"], history, **options)
            add_receipt(answer, case, pending["text"], pending.get("image_ids", []), history)
            assistant = {
                "role": "assistant",
                "created_at": now(),
                "resolved_question_id": pending["id"],
                **answer,
            }
            if answer.get("provider") != "clarification":
                case.pop("pending_question", None)
                store.add_message(case_id, assistant)
            case["updated_at"] = now()
            store.save(x_client_id, case)
            return assistant

    @app.post(
        "/api/cases/{case_id}/messages",
        status_code=201,
        dependencies=[Depends(require_account)],
    )
    async def message(
        case_id: str, body: MessageRequest, x_client_id: str = Header(default="")
    ):
        text = body.text.strip()
        if not text:
            raise HTTPException(422, "请输入问题")
        with mutation(case_id):
            case = get_case(x_client_id, case_id)
            history = store.messages(case_id)
            if body.request_id:
                existing = next(
                    (
                        message
                        for message in reversed(history)
                        if message.get("request_id") == body.request_id
                        and message["role"] == "assistant"
                    ),
                    None,
                )
                if existing:
                    return existing
            crop_changed = crop_scope_conflicts(case.get("crop"), query_crop_scope(text))
            if not crop_changed and not is_general_question(text):
                fill_explicit_context(case, text)
            documents = [
                document
                for document in case.get("documents", [])
                if document["id"] in body.attachment_ids
            ]
            images = [
                image for image in case["images"] if image["id"] in body.image_ids
            ]
            if len(documents) != len(set(body.attachment_ids)) or len(images) != len(
                set(body.image_ids)
            ):
                raise HTTPException(422, "附件不属于这条对话")
            if not crop_changed and case.get("stage") in ("", "不清楚"):
                for previous in reversed(history):
                    if (
                        previous["role"] == "user"
                        and not is_general_question(previous["text"])
                        and not crop_scope_conflicts(
                            case.get("crop"), query_crop_scope(previous["text"])
                        )
                    ):
                        fill_explicit_context(case, previous["text"])
                    if case.get("stage") not in ("", "不清楚"):
                        break
            validate_options(body.model, body.web_search)
            # 资料更新只确认保存；新问题直接回答。旧待答问题仅由 /resume 主动接续。
            context_answer = (
                optional_context_response(case, text, history)
                if not body.image_ids and not body.attachment_ids and not crop_changed
                else None
            )
            answer = context_answer or await chat.answer(
                case, text, history, body.model, body.thinking, web_search=body.web_search
            )
            add_receipt(answer, case, text, body.image_ids, history)
            if context_answer is None and answer.get("notice_code") != "crop_mismatch":
                case.pop("pending_question", None)
            user_message = {
                "role": "user",
                "text": text,
                "created_at": now(),
                "sources": [],
                "provider": "user",
                "products": [],
                "attachments": [
                    {"id": document["id"], "name": document["name"], "kind": "document"}
                    for document in documents
                ]
                + [
                    {"id": image["id"], "name": "症状照片", "kind": "image"}
                    for image in images
                ],
            }
            assistant = {"role": "assistant", "created_at": now(), **answer}
            if body.request_id:
                user_message["request_id"] = body.request_id
                assistant["request_id"] = body.request_id
            store.add_exchange(case_id, user_message, assistant)
            case["updated_at"] = now()
            store.save(x_client_id, case)
            return assistant

    @app.delete("/api/cases/{case_id}", status_code=204)
    def delete_case(case_id: str, x_client_id: str = Header(default="")):
        with mutation(case_id):
            case = get_case(x_client_id, case_id)
            store.delete(x_client_id, case_id)
            folder = settings.runtime / "images" / case_id
            # Only generated image paths referenced by this owned case are removed.
            for img in case["images"]:
                (folder / (img["id"] + ".jpg")).unlink(missing_ok=True)
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
            return

    web = settings.root / "apps/client/dist/build/h5"
    if settings.serve_web and web.is_dir():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app
