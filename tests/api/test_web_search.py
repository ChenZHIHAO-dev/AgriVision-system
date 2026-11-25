import asyncio
from pathlib import Path
import httpx
import pytest
from app.chat import Chat
from app.config import Settings
from app.knowledge import Knowledge

ROOT = Path(__file__).resolve().parents[2]


def test_optional_web_search_returns_actual_citations_without_exposing_provider_internals(
    tmp_path, monkeypatch
):
    payload = {}

    async def respond(_self, url, **kwargs):
        payload.update(kwargs["json"])
        message = {
            "content": "请根据当地农技部门资料核对症状，并记录发生范围。",
            "annotations": [
                {
                    "type": "url_citation",
                    "url_citation": {
                        "url": "https://example.org/agri",
                        "title": "公开农技资料",
                    },
                }
            ],
            "server_tool_calls": [
                {
                    "reasoning_content": "PRIVATE_PROVIDER_REASONING",
                    "calls": [{"type": "deepseek_web_search", "status": "completed"}],
                }
            ],
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": message}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", respond)
    settings = Settings(
        root=ROOT, runtime=tmp_path, models=tmp_path, deepseek_key="fake-test-value"
    )
    case = {
        "crop": "wheat",
        "stage": "苗期",
        "location": "南阳",
        "note": "",
        "is_demo": False,
        "status": "awaiting_image",
        "disease_id": None,
    }
    answer = asyncio.run(
        Chat(settings, Knowledge(ROOT)).answer(
            case, "请查阅公开农技资料", [], web_search=True
        )
    )
    assert payload["tools"] == [{"type": "deepseek_web_search"}]
    assert answer["web_search_used"] is True
    assert answer["sources"][0]["url"] == "https://example.org/agri"
    assert "PRIVATE_PROVIDER_REASONING" not in str(answer)


def test_pro_web_combination_is_explicitly_rejected(tmp_path):
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path)
    with pytest.raises(ValueError, match="Flash"):
        asyncio.run(
            Chat(settings, Knowledge(ROOT)).answer(
                {}, "问题", [], "deepseek-v4-pro", web_search=True
            )
        )
