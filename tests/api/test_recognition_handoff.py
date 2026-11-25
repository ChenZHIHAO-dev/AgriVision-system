import asyncio
from io import BytesIO
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest

from app.chat import Chat
from app.config import Settings
from app.knowledge import Knowledge
from app.application import create_app
from app.recognition import recognition_state

ROOT = Path(__file__).resolve().parents[2]


def example(status="identified"):
    return {
        "crop": "wheat",
        "stage": "苗期",
        "location": "南阳",
        "note": "",
        "is_demo": False,
        "status": status,
        "title": "疑似小麦白粉病",
        "disease_id": "wheat_powdery_mildew" if status == "identified" else None,
        "model_version": "test-cnn",
        "experimental": True,
        "images": [
            {
                "id": "test-image",
                "url": "NEVER_SEND_IMAGE_URL",
                "quality": {"issues": ["图像细节不足"]},
            }
        ],
        "candidates": [
            {"id": "wheat_powdery_mildew", "name": "小麦白粉病", "score": 0.994}
        ],
    }


@pytest.mark.parametrize(
    "status,outcome",
    [
        ("identified", "supported_result"),
        ("uncertain", "low_confidence"),
        ("needs_retake", "quality_check_failed"),
        ("needs_model", "model_unavailable"),
        ("model_error", "service_error"),
    ],
)
def test_every_processed_image_gets_an_explicit_receipt(status, outcome):
    receipt = recognition_state(example(status))
    assert receipt["image_received"] is True and receipt["outcome"] == outcome
    assert "照片已" in receipt["summary"]
    if status != "identified":
        assert receipt["next_steps"]


def test_latest_cnn_result_survives_a_stale_no_image_history(tmp_path, monkeypatch):
    seen = {}

    async def respond(_self, url, **kwargs):
        seen.update(kwargs["json"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "照片已收到。识别模型初步提示小麦白粉病，请补拍叶背和植株下部，核对是否有白色粉状物。"
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", respond)
    settings = Settings(
        root=ROOT, runtime=tmp_path, models=tmp_path, deepseek_key="fake-test-value"
    )
    answer = asyncio.run(
        Chat(settings, Knowledge(ROOT)).answer(
            example(),
            "请解释刚刚的结果",
            [{"role": "assistant", "text": "我没有收到图片，也没有图像识别结果。"}],
        )
    )
    assert answer["provider"] == "deepseek" and "白粉病" in answer["text"]
    payload = json.dumps(seen, ensure_ascii=False)
    assert "NEVER_SEND_IMAGE_URL" not in payload
    assert "我没有收到图片" not in payload
    latest = json.loads(seen["messages"][-2]["content"].split("\n", 1)[1])
    assert (
        latest["image_received"] is True
        and latest["disease_id"] == "wheat_powdery_mildew"
    )


def test_contradictory_provider_reply_is_replaced_with_the_actual_result(
    tmp_path, monkeypatch
):
    async def respond(_self, url, **_kwargs):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "我依然没有收到图片，系统也没有返回图像识别结果。"
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", respond)
    settings = Settings(
        root=ROOT, runtime=tmp_path, models=tmp_path, deepseek_key="fake-test-value"
    )
    answer = asyncio.run(
        Chat(settings, Knowledge(ROOT)).answer(example(), "刚才识别到了什么？", [])
    )
    assert answer["notice_code"] == "inconsistent_recognition"
    assert "白粉病" in answer["text"] and "照片已收到" in answer["text"]
    assert "没有收到" not in answer["text"]


def test_standalone_recognition_never_calls_chat_and_unknown_stage_preserves_known_context(
    tmp_path, monkeypatch, account_headers, admin_hash
):
    settings = Settings(
        root=ROOT, runtime=tmp_path / "runtime", models=tmp_path / "models", admin_password_hash=admin_hash
    )
    app = create_app(settings)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError(
            "Standalone recognition must not call a conversation provider"
        )

    monkeypatch.setattr(app.state.chat, "answer", forbidden)
    monkeypatch.setattr(
        app.state.registry,
        "predict",
        lambda *_args: {
            key: value
            for key, value in example().items()
            if key
            in {
                "status",
                "title",
                "disease_id",
                "model_version",
                "experimental",
                "candidates",
            }
        },
    )
    image = Image.fromarray(
        np.random.default_rng(42).integers(20, 230, (400, 500, 3), dtype=np.uint8)
    )
    stream = BytesIO()
    image.save(stream, "JPEG")
    with TestClient(app) as client:
        headers = account_headers(client)
        case = client.post(
            "/api/consultations",
            headers=headers,
            json={"crop": "wheat", "stage": "苗期"},
        ).json()
        result = client.post(
            f"/api/cases/{case['id']}/images",
            headers=headers,
            data={"crop": "wheat", "stage": "不清楚"},
            files={"file": ("test.jpg", stream.getvalue(), "image/jpeg")},
        )
        assert result.status_code == 200
        record = result.json()
        assert record["stage"] == "苗期"
        assert record["recognition"]["image_received"] is True
        assert record["recognition"]["disease_id"] == "wheat_powdery_mildew"
        assert record["messages"] == [] and "白粉病" in record["advice"]["summary"]


def test_latest_context_and_known_stage_override_stale_clarification(
    tmp_path, monkeypatch
):
    seen = {}

    async def respond(_self, url, **kwargs):
        seen.update(kwargs["json"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "### 建议\n请先观察叶片两面。\n\n请补充小麦当前生育期。"
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", respond)
    case = example()
    case["images"][0]["stage"] = "不清楚"
    settings = Settings(
        root=ROOT, runtime=tmp_path, models=tmp_path, deepseek_key="fake-test-value"
    )
    answer = asyncio.run(
        Chat(settings, Knowledge(ROOT)).answer(
            case,
            "请继续回答",
            [
                {
                    "role": "assistant",
                    "provider": "clarification",
                    "text": "STALE_CLARIFICATION",
                }
            ],
        )
    )
    latest = json.loads(seen["messages"][-2]["content"].split("\n", 1)[1])
    assert latest["context"]["stage"] == "苗期"
    assert latest["image_results"][0]["stage"] == "苗期"
    assert "STALE_CLARIFICATION" not in json.dumps(seen)
    assert "观察叶片两面" in answer["text"] and "请补充" not in answer["text"]
