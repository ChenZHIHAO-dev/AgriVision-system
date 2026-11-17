from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import uuid
from threading import Lock

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .chat import Chat
from .config import Settings
from .imaging import prepare_image
from .knowledge import Knowledge, CROP_NAMES
from .models import ModelRegistry
from .schemas import Crop, DemoRequest, MessageRequest, CaseUpdate
from .store import Store


def now():
    return datetime.now(timezone.utc).isoformat()


def create_app(settings=None):
    settings = settings or Settings.from_env()
    store = Store(settings.runtime / "agrivision.sqlite3")
    knowledge = Knowledge(settings.root)
    registry = ModelRegistry(settings, knowledge)
    chat = Chat(settings, knowledge)
    case_locks = {}
    lock_guard = Lock()

    app = FastAPI(title="AgriVision API", version="1.0.0-dev.1")
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors), allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-Client-ID"])
    app.state.registry = registry
    app.state.store = store
    app.state.chat = chat

    @contextmanager
    def mutation(case_id):
        with lock_guard:
            lock = case_locks.setdefault(case_id, Lock())
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "这条问诊正在处理，请稍候重试")
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
            raise HTTPException(404, "问诊记录不存在")
        return case

    def serialize(case):
        result = dict(case)
        result["advice"] = knowledge.advice(case["crop"], case.get("disease_id"), case["is_demo"], case["stage"])
        result["messages"] = store.messages(case["id"])
        return result

    def base_case(crop, location="河南省 / 南阳市", stage="不清楚", note=""):
        timestamp = now()
        return {"id": uuid.uuid4().hex, "crop": crop, "crop_name": CROP_NAMES[crop], "location": location, "stage": stage, "note": note, "created_at": timestamp, "updated_at": timestamp, "is_demo": False, "images": [], "versions": [], "status": "needs_model", "title": "图片已保存，识别模型准备中", "candidates": [], "disease_id": None, "model_version": None}

    async def apply_upload(case, upload):
        content = await upload.read(settings.max_upload + 1)
        await upload.close()
        if len(content) > settings.max_upload:
            raise HTTPException(413, "图片不能超过 8MB，请压缩后重试")
        try:
            normalized, quality = prepare_image(content)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        image_id = uuid.uuid4().hex
        folder = settings.runtime / "images" / case["id"]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (image_id + ".jpg")
        path.write_bytes(normalized)
        case["images"].append({"id": image_id, "quality": quality, "created_at": now()})
        if quality["issues"]:
            prediction = {"status": "needs_retake", "title": "需要一张更清晰的症状照片", "candidates": [], "disease_id": None, "model_version": None}
        else:
            from starlette.concurrency import run_in_threadpool
            prediction = await run_in_threadpool(registry.predict, case["crop"], path)
        case.update(prediction)
        case["versions"].append({**prediction, "image_id": image_id, "created_at": now()})
        case["updated_at"] = now()
        return case

    @app.get("/api/health")
    def health():
        return {"application": "agrivision", "status": "ok", "version": app.version}

    @app.get("/api/meta")
    def meta():
        return {"version": app.version, "models": registry.status(), "deepseek_configured": bool(settings.deepseek_key), "knowledge_count": len(knowledge.cards), "product_count": len([p for p in knowledge.products if p.approved]), "max_upload_mb": 8, "mode": "local-development"}

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
        return {"items": store.list(owner(x_client_id))}

    @app.post("/api/cases/demo", status_code=201)
    def demo(body: DemoRequest, x_client_id: str = Header(default="")):
        client = owner(x_client_id)
        disease = {"wheat": "wheat_stripe_rust", "maize": "maize_southern_rust", "peanut": "peanut_leaf_spot"}[body.crop]
        card = knowledge.get(disease)
        case = base_case(body.crop, stage="演示阶段", note="此记录为功能演示，不是对用户照片的识别结果")
        case.update({"is_demo": True, "status": "demo", "title": card["title"] + " · 演示样例", "disease_id": disease})
        store.save(client, case)
        return serialize(case)

    @app.post("/api/cases", status_code=201)
    async def create_case(file: UploadFile = File(...), crop: Crop = Form(...), location: str = Form(default="河南省 / 南阳市", max_length=120), stage: str = Form(default="不清楚", max_length=40), note: str = Form(default="", max_length=2000), x_client_id: str = Header(default="")):
        client = owner(x_client_id)
        case = await apply_upload(base_case(crop, location, stage, note), file)
        store.save(client, case)
        return serialize(case)

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str, x_client_id: str = Header(default="")):
        return serialize(get_case(x_client_id, case_id))

    @app.post("/api/cases/{case_id}/context")
    def update_case(case_id: str, body: CaseUpdate, x_client_id: str = Header(default="")):
        with mutation(case_id):
            case = get_case(x_client_id, case_id)
            case.update(body.model_dump(exclude_none=True))
            case["updated_at"] = now()
            store.save(x_client_id, case)
            return serialize(case)

    @app.post("/api/cases/{case_id}/images")
    async def supplement(case_id: str, file: UploadFile = File(...), x_client_id: str = Header(default="")):
        with mutation(case_id):
            case = get_case(x_client_id, case_id)
            if case["is_demo"]:
                raise HTTPException(409, "请新建真实图片问诊，演示记录不接收用户图片")
            if len(case["images"]) >= 6:
                raise HTTPException(422, "同一问诊最多保存 6 张图片")
            case = await apply_upload(case, file)
            store.save(x_client_id, case)
            return serialize(case)

    @app.get("/api/cases/{case_id}/images/{image_id}")
    def image(case_id: str, image_id: str, client_id: str):
        case = get_case(client_id, case_id)
        if not any(img["id"] == image_id for img in case["images"]):
            raise HTTPException(404, "图片不存在")
        return FileResponse(settings.runtime / "images" / case_id / (image_id + ".jpg"), media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})

    @app.post("/api/cases/{case_id}/messages", status_code=201)
    async def message(case_id: str, body: MessageRequest, x_client_id: str = Header(default="")):
        text = body.text.strip()
        if not text:
            raise HTTPException(422, "请输入问题")
        with mutation(case_id):
            case = get_case(x_client_id, case_id)
            history = store.messages(case_id)
            answer = await chat.answer(case, text, history)
            user_message = {"role": "user", "text": text, "created_at": now(), "sources": [], "provider": "user", "products": []}
            assistant = {"role": "assistant", "created_at": now(), **answer}
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
            return None

    web = settings.root / "apps/client/dist/build/h5"
    if web.is_dir():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app


app = create_app()
