"""Exercise the local HTTP API. Does not read provider credential files.

Default checks use only guest recognition and access checks. --username also tests the
login handoff and local intake. --exercise-provider and --web make paid dialogue requests.
"""

import argparse
import csv
import json
import re
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
        raise ValueError('Provider checks require a test account')
    headers = {"X-Client-ID": "local-verification-" + uuid.uuid4().hex}
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "scope": "local functional check using a photo from the current wheat leaf and spike test split",
        "credential_access": "HTTP API only; no credential-file access",
        "dialogue": [],
    }
    case_id = None
    with httpx.Client(base_url=base, headers=headers, timeout=160) as client:

        def post(path, **kwargs):
            response = client.post(path, **kwargs)
            response.raise_for_status()
            return response.json()

        health = client.get("/api/health")
        health.raise_for_status()
        report["api_version"] = health.json()["version"]

        try:
            dataset = ROOT / "data/wheat-leaf-spike-03"
            with (dataset / "manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
                row = next(
                    row
                    for row in csv.DictReader(stream)
                    if row["split"] == "test" and row["label"] == "wheat_powdery_mildew"
                )
            image = dataset / "images" / row["path"]
            case = post(
                "/api/cases",
                data={"crop": "wheat"},
                files={"file": ("held-out.jpg", image.read_bytes(), "image/jpeg")},
            )
            case_id = case["id"]
            path = "/api/cases/" + case_id
            assert case["recognition"]["image_received"]
            assert (
                len(case["messages"]) == 2
                and case["messages"][1]["provider"] == "recognition"
            )
            first_id = case["images"][0]["id"]
            report["standalone"] = {
                "status": case["status"],
                "disease_id": case["disease_id"],
                "model_version": case["model_version"],
                "transcript_provider": "recognition",
                "dialogue_provider_called": False,
                "persistence": case["persistence"],
            }
            control = BytesIO()
            Image.new("RGB", (320, 320), (128, 128, 128)).save(control, "JPEG")
            case = post(
                path + "/images",
                files={
                    "file": (
                        "synthetic-quality-control.jpg",
                        control.getvalue(),
                        "image/jpeg",
                    )
                },
            )
            receipt = case["recognition"]
            assert receipt["image_count"] == 2 and not case["candidates"]
            assert receipt["image_results"][0]["image_id"] == first_id
            assert len(case["messages"]) == 2
            report["multi_image"] = {
                "outcome": receipt["outcome"],
                "per_image_status": [
                    item["status"] for item in receipt["image_results"]
                ],
                "aggregate_probability": False,
                "second_input": "synthetic quality control",
                "photo_upload_triggered_dialogue": False,
            }
            guest_checks = {
                '/api/consultations': {'crop': 'wheat'},
                path + '/messages': {'text': '请解释现有图片识别结果。'},
                path + '/resume': {'question_id': 'pending-check'},
            }
            for endpoint, payload in guest_checks.items():
                assert client.post(endpoint, json=payload).status_code == 401, endpoint
            report['guest_dialogue_blocked'] = True
            if account is None:
                report['passed'] = True
                return report

            login = post('/api/auth/login', json={**account, 'continue_case_id': case_id})
            client.headers['Authorization'] = 'Bearer ' + login["access_token"]
            assert login['continued_case_id'] == case_id
            restored = client.get(path)
            restored.raise_for_status()
            assert restored.json()['images'][0]['id'] == first_id
            report['login_handoff'] = {'case_retained': True, 'photo_retained': True}
            clarification = post(
                path + "/messages", json={"text": "这株小麦的叶片有斑点，现在应该怎么观察和处理？"}
            )
            assert clarification["provider"] == "clarification"
            before = len(client.get(path).json()["messages"])
            case = post(
                path + "/context", json={"stage": "苗期", "location": "河南省 / 南阳市"}
            )
            assert len(case["messages"]) == before
            report["context_collection"] = {
                "provider": "program",
                "selection_added_messages": False,
                "selection_called_dialogue_provider": False,
            }
            document_response = client.post(
                path + "/attachments",
                files={
                    "file": (
                        "field-notes.txt",
                        "示例：小麦苗期，叶片零星出现黄斑。".encode("utf-8"),
                        "text/plain",
                    )
                },
            )
            document_response.raise_for_status()
            document = document_response.json()["documents"][0]
            assert document["extraction"] == "ready" and "text" not in document
            report["document"] = {"extraction": document["extraction"]}

            if exercise_provider:
                question_id = clarification["pending_question_id"]
                started = time.perf_counter()
                answer = post(
                    path + "/resume",
                    json={
                        "question_id": question_id,
                        "model": "deepseek-flash",
                        "thinking": False,
                    },
                )
                completed = client.get(path).json()
                replay = post(path + "/resume", json={"question_id": question_id})
                assert answer == replay
                assert len(completed["messages"]) == before + 1
                assert "pending_question" not in completed
                assert completed["messages"][-2]["provider"] == "clarification"
                assert answer["provider"] == "deepseek"
                assert not re.search(
                    r"(没有|没|未)收到.{0,8}(图片|照片)", answer["text"]
                )
                report["resume"] = {
                    "original_question_retained": True,
                    "assistant_messages_added": 1,
                    "synthetic_user_messages_added": 0,
                    "idempotent_replay": True,
                    "provider": answer["provider"],
                    "model": answer.get("model"),
                    "seconds": round(time.perf_counter() - started, 2),
                }
            modes = [("deepseek-v4-pro", True, False)] if exercise_provider else []
            if web:
                modes.append(("deepseek-flash", False, True))
            for model, thinking, search in modes:
                question = (
                    "请联网查询小麦近期农业气象信息，给出可核验的来源与发布日期，150字以内。"
                    if search
                    else "请结合小麦照片和上传的田间记录，区分已识别和未判明的照片，给出下一步观察建议，150字以内。"
                )
                started = time.perf_counter()
                answer = post(
                    path + "/messages",
                    json={
                        "text": question,
                        "model": model,
                        "thinking": thinking,
                        "web_search": search,
                        "attachment_ids": [] if search else [document["id"]],
                    },
                )
                item = {
                    "model": model,
                    "thinking": thinking,
                    "web_requested": search,
                    "provider": answer["provider"],
                    "characters": len(answer["text"]),
                    "source_count": len(answer.get("sources", [])),
                    "web_search_used": answer.get("web_search_used", False),
                    "notice_code": answer.get("notice_code"),
                    "seconds": round(time.perf_counter() - started, 2),
                }
                report["dialogue"].append(item)
                assert not re.search(
                    r"(没有|没|未)收到.{0,8}(图片|照片)", answer["text"]
                )
                assert not re.search(r"请补充.{0,10}生育期", answer["text"])
                assert answer["provider"] == "deepseek", (
                    "Provider did not complete the dialogue"
                )
                if search:
                    assert item["web_search_used"] and item["source_count"], (
                        "Web tool did not return actual sources"
                    )
            report["passed"] = True
        finally:
            if case_id:
                client.delete("/api/cases/" + case_id)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--exercise-provider", action="store_true")
    parser.add_argument("--web", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--username", help="Test account for checking consultation after login")
    args = parser.parse_args()
    if (args.exercise_provider or args.web) and not args.username:
        parser.error("付费对话验收需要通过 --username 指定测试账号")
    account = None
    if args.username:
        account = {"username": args.username, "password": getpass("测试账号密码：")}
    result = run(args.base, args.exercise_provider, args.web, account=account)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
