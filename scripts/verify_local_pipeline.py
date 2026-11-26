"""通过真实 HTTP 检查联调服务；不读取 DeepSeek 密钥文件。

默认只测公开健康信息和匿名拒绝。--username 在终端隐藏输入管理员密码，
再测照片、资料、附件和退出。只有 --exercise-provider/--web 才调用付费问答。
"""
import argparse
import csv
import json
import time
import uuid
from datetime import UTC, datetime
from getpass import getpass
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def run(base, exercise_provider=False, web=False, *, account=None):
    if (exercise_provider or web) and account is None:
        raise ValueError("付费对话验收需要管理员账户")
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "scope": "HTTP functional check; selected internal photo is not an accuracy benchmark",
        "credential_access": "HTTP account only; no provider credential-file access",
        "dialogue": [],
    }
    # 客户端 ID 仅是请求标识，不能代替服务器会话获得访问权限。
    headers = {"X-Client-ID": "local-verification-" + uuid.uuid4().hex}
    case_ids = []
    with httpx.Client(base_url=base, headers=headers, timeout=160) as client:
        def post(path, **kwargs):
            response = client.post(path, **kwargs)
            response.raise_for_status()
            return response.json()

        health = client.get("/api/health")
        health.raise_for_status()
        report["api_version"] = health.json()["version"]
        anonymous = [("GET", "/api/cases"), ("GET", "/api/knowledge"),
                     ("POST", "/api/cases"), ("POST", "/api/crop-recognition"),
                     ("POST", "/api/consultations")]
        for method, endpoint in anonymous:
            # 不附带图片或完整请求体，验证必须先鉴权，不能先解码或推理。
            response = client.request(method, endpoint)
            assert response.status_code == 401, (endpoint, response.status_code)
        assert client.post("/api/auth/register", json={}).status_code == 403
        report["anonymous_business_blocked"] = True
        report["self_registration_disabled"] = True
        if account is None:
            report["passed"] = True
            report["authenticated_checks"] = "not requested; rerun with --username admin"
            return report

        login = post("/api/auth/login", json=account)
        client.headers["Authorization"] = "Bearer " + login["access_token"]
        try:
            dataset = ROOT / "data/wheat/prepared"
            with (dataset / "manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
                row = next(row for row in csv.DictReader(stream)
                           if row["split"] == "test" and row["label"] == "wheat_powdery_mildew")
            image = dataset / "images" / row["path"]
            started = time.perf_counter()
            case = post("/api/cases", data={"crop": "wheat"},
                        files={"file": ("held-out.jpg", image.read_bytes(), "image/jpeg")})
            case_ids.append(case["id"])
            path = "/api/cases/" + case["id"]
            assert case["recognition"]["image_received"]
            assert len(case["messages"]) == 2 and case["messages"][1]["provider"] == "recognition"
            first_id = case["images"][0]["id"]
            report["standalone"] = {
                "status": case["status"], "disease_id": case["disease_id"],
                "model_version": case["model_version"], "persistence": case["persistence"],
                "dialogue_provider_called": False, "seconds": round(time.perf_counter()-started, 3),
            }
            # 纯色控制图验证质量拒绝与证据保留，不伪装成真实病害照片。
            control = BytesIO()
            Image.new("RGB", (320, 320), (128, 128, 128)).save(control, "JPEG")
            case = post(path + "/images", files={"file": (
                "synthetic-quality-control.jpg", control.getvalue(), "image/jpeg")})
            receipt = case["recognition"]
            assert receipt["image_count"] == 2 and not case["candidates"]
            assert receipt["image_results"][0]["image_id"] == first_id
            assert len(case["messages"]) == 2
            report["multi_image"] = {"outcome": receipt["outcome"],
                "per_image_status": [item["status"] for item in receipt["image_results"]],
                "photo_upload_triggered_dialogue": False}

            before = len(case["messages"])
            case = post(path + "/context", json={"stage": "苗期", "location": "河南省 / 南阳市"})
            assert len(case["messages"]) == before
            report["optional_context"] = {"selection_added_messages": False,
                                          "selection_called_dialogue_provider": False}
            document_case = post(path + "/attachments", files={"file": (
                "field-notes.txt", "示例：小麦苗期，叶片零星出现黄斑。".encode("utf-8"), "text/plain")})
            document = document_case["documents"][0]
            assert document["extraction"] == "ready" and "text" not in document
            report["document"] = {"extraction": document["extraction"]}

            # 新对话不应先弹必填表。新建动作本身不调用模型；用户发送才请求回答。
            conversation = post("/api/consultations", json={"crop": "wheat"})
            case_ids.append(conversation["id"])
            assert not conversation.get("pending_question")
            report["new_conversation"] = {"required_intake": False}
            modes = [("deepseek-flash", False, False)] if exercise_provider else []
            if web:
                modes.append(("deepseek-flash", False, True))
            for model, thinking, search in modes:
                question = ("请查询近期小麦农业气象信息，注明可核验来源和日期，150字以内。" if search
                            else "请结合已有小麦照片和田间记录说明还不能确定的地方，并给出观察建议，150字以内。")
                started = time.perf_counter()
                answer = post(path + "/messages", json={"text": question, "model": model,
                    "thinking": thinking, "web_search": search,
                    "attachment_ids": [] if search else [document["id"]]})
                assert answer["provider"] == "deepseek", "外部问答未完成"
                assert not answer.get("pending_question_id"), "回答不应被必填补问阻塞"
                report["dialogue"].append({"model": model, "provider": answer["provider"],
                    "characters": len(answer["text"]), "source_count": len(answer.get("sources", [])),
                    "web_search_used": answer.get("web_search_used", False),
                    "seconds": round(time.perf_counter()-started, 2)})
                if search:
                    assert answer.get("web_search_used") and answer.get("sources")
            report["passed"] = True
        finally:
            # 仅删除本次脚本创建的记录。先清理再退出，避免留下测试照片和附件。
            cleanup = []
            for identifier in reversed(case_ids):
                response = client.delete("/api/cases/" + identifier)
                cleanup.append(response.status_code in {200, 204, 404})
            response = client.post("/api/auth/logout")
            response.raise_for_status()
            report["cleanup_complete"] = all(cleanup)
            assert client.get("/api/cases").status_code == 401
            report["logout_invalidates_session"] = True
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--exercise-provider", action="store_true")
    parser.add_argument("--web", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--username", help="内测账号；密码在终端隐藏输入，不写在命令中")
    args = parser.parse_args()
    if (args.exercise_provider or args.web) and not args.username:
        parser.error("付费对话验收需要 --username admin")
    account = {"username": args.username, "password": getpass("内测账号密码：")} if args.username else None
    result = run(args.base, args.exercise_provider, args.web, account=account)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
