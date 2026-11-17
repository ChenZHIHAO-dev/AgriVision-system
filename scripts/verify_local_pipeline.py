"""Exercise the local HTTP API. Does not read provider credential files.

Default checks use local recognition only. --exercise-provider makes two paid
dialogue requests (including intake resume); --web additionally checks Flash's optional web tool.
"""

import argparse
import csv
import json
import re
import time
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def run(base, exercise_provider=False, web=False):
    headers = {"X-Client-ID": "local-verification-" + uuid.uuid4().hex}
    report = {
        "version": "1.2.2-dev.1",
        "checked_at": datetime.now(UTC).isoformat(),
        "scope": "local functional check; internal held-out image, not a new accuracy evaluation",
        "credential_access": "HTTP API only; no credential-file access",
        "dialogue": [],
    }
    case_id = None
    with httpx.Client(base_url=base, headers=headers, timeout=160) as client:

        def post(path, **kwargs):
            response = client.post(path, **kwargs)
            response.raise_for_status()
            return response.json()

        try:
            rows = csv.DictReader(
                (ROOT / "data/wheat-v1/manifest.csv").open(encoding="utf-8-sig")
            )
            row = next(
                row
                for row in rows
                if row["split"] == "test" and row["label"] == "wheat_powdery_mildew"
            )
            image = ROOT / "data/wheat-v1/images" / row["path"]
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
            clarification = post(
                path + "/messages", json={"text": "请解释现有图片识别结果。"}
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
                    else "请解释现有图片识别线索，区分已识别和未判明的照片，给出下一步观察建议，150字以内。"
                )
                started = time.perf_counter()
                answer = post(
                    path + "/messages",
                    json={
                        "text": question,
                        "model": model,
                        "thinking": thinking,
                        "web_search": search,
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
    args = parser.parse_args()
    result = run(args.base, args.exercise_provider, args.web)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
