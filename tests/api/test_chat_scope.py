"""Agricultural routing happens before credentials or any paid provider/search."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.chat import Chat, SCOPE_GUIDANCE, within_agricultural_scope
from app.knowledge import Knowledge

ROOT = Path(__file__).resolve().parents[2]


def case(**overrides):
    return {
        "crop": None,
        "stage": "不清楚",
        "location": "",
        "note": "",
        "status": "awaiting_image",
        "title": "文字咨询",
        "disease_id": None,
        "is_demo": False,
        "images": [],
        "documents": [],
        **overrides,
    }


@pytest.mark.parametrize("text", [
    "帮我写一个爬虫",
    "什么是人工智能？",
    "小麦先不说了，推荐一部电影",
    "农药的问题稍后再说，帮我写一段代码",
    "推荐股票，今天买什么？",
    "小麦期货怎么买？",
    "玉米怎么投保？",
    "玉米保险怎么买？",
    "小麦条锈病能申请理赔吗？",
    "农业贷款怎么申请？",
    "Can I buy wheat futures?",
    "What crop insurance should I buy for maize?",
    "How do I get a peanut farm loan?",
    "给我一份旅游攻略",
    "怎么修电脑蓝屏？",
    "what is quantum mechanics?",
])
@pytest.mark.parametrize("has_context", [False, True])
def test_unrelated_questions_never_read_credentials_or_call_provider(text, has_context, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("out-of-scope routing must not load a key, search, or call a provider")

    monkeypatch.setattr(httpx.AsyncClient, "post", forbidden)
    settings = SimpleNamespace(deepseek_model="deepseek-flash", get_deepseek_key=forbidden)
    knowledge = SimpleNamespace(search=forbidden)
    record = case(crop="wheat", stage="苗期") if has_context else case()
    history = [{"role": "user", "text": "小麦叶片发黄怎么办？"}] if has_context else []
    result = asyncio.run(Chat(settings, knowledge).answer(record, text, history, web_search=True))
    assert result["text"] == SCOPE_GUIDANCE
    assert result["provider"] == "rules"
    assert result["notice_code"] == "out_of_scope"
    assert result["web_search_used"] is False
    assert result["web_search_enabled"] is False
    assert result["sources"] == result["products"] == []
    assert "follow_up" not in result


@pytest.mark.parametrize("text", [
    "什么是小麦条锈病？",
    "生育期是什么意思？",
    "怎么看农药标签？",
    "如何拍清楚症状？",
    "叶片有黄斑，应该怎么观察？",
    "玉米大喇叭口期怎么管理？",
    "肥料有什么作用？",
    "What is wheat rust?",
    "小麦用药怎么做更保险？",
])
def test_no_photo_agricultural_questions_are_admitted(text):
    settings = SimpleNamespace(deepseek_model="deepseek-flash", get_deepseek_key=lambda: "")
    result = asyncio.run(Chat(settings, Knowledge(ROOT)).answer(case(), text, []))
    assert result.get("notice_code") != "out_of_scope"
    assert result["provider"] in {"knowledge", "clarification", "rules"}


@pytest.mark.parametrize("text", [
    "怎么办？", "接着说说检查方法。", "需要补充什么信息？", "用什么药？",
    "先说明排查方向", "请回答刚才的问题。", "用药前需要核对什么？",
])
def test_short_followups_require_actual_conversation_context(text):
    assert not within_agricultural_scope(case(), text, [])
    assert within_agricultural_scope(case(crop="wheat"), text, [])
    assert within_agricultural_scope(case(), text, [{"role": "user", "text": "叶片上有黄斑"}])
    # A generic assistant greeting/guard reply does not manufacture user context.
    assert not within_agricultural_scope(case(), text, [{"role": "assistant", "text": SCOPE_GUIDANCE}])


def test_attachment_summary_needs_agricultural_body_evidence():
    unrelated = {"name": "小麦资料.txt", "text": "这是一个软件部署与数据库配置教程。"}
    agricultural = {"name": "记录.txt", "text": "田间小麦苗期叶片出现零星黄斑。"}
    assert not within_agricultural_scope(case(crop="wheat", documents=[unrelated]), "请总结附件", [])
    assert not within_agricultural_scope(case(documents=[unrelated]), "请根据资料说明", [])
    assert within_agricultural_scope(case(documents=[agricultural]), "请总结附件", [])
    # An agricultural document cannot authorize a new unrelated task.
    assert not within_agricultural_scope(case(documents=[agricultural]), "根据资料帮我写Python代码", [])


def test_agricultural_text_reaches_mock_provider_with_scope_prompt(monkeypatch):
    seen = {}

    async def respond(self, url, **kwargs):
        seen.update(kwargs["json"])
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "先检查小麦叶片两面和田间分布。"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", respond)
    settings = SimpleNamespace(
        deepseek_model="deepseek-flash",
        deepseek_url="https://unit.invalid",
        get_deepseek_key=lambda: "fake-scope-test-key",
    )
    record = case(crop="wheat", stage="苗期")
    result = asyncio.run(Chat(settings, Knowledge(ROOT)).answer(record, "小麦叶片发黄怎么观察？", []))
    assert record["images"] == []
    assert result["provider"] == "deepseek"
    system = seen["messages"][0]["content"]
    assert "只回答农作物病虫害" in system
    assert "农业历史不代表可以回答新出现的无关问题" in system
    assert "混合问题只回答农业部分" in system
    assert "期货交易、保险投保或理赔、贷款、投资" in system
    assert "tools" not in seen


@pytest.mark.parametrize("text", [
    "这次照片的画质检查没有通过，请说明具体该怎样补拍。",
    "照片已上传但目前还不能可靠判断，请结合逐张处理回执说明还要观察或补充什么。",
    "请结合这组照片的逐张识别回执，解释已有线索、未判明的部分和下一步建议。",
    "请解释刚刚的结果", "请解释这个结果", "刚才识别到了什么？", "这张照片需要补拍吗？",
])
def test_first_party_photo_report_requests_require_a_stored_photo(text):
    assert within_agricultural_scope(case(images=[{"id": "photo-1"}]), text, [])
    assert not within_agricultural_scope(case(crop="wheat"), text, [])
    assert not within_agricultural_scope(case(recognition={"image_received": True}), text, [])
    assert not within_agricultural_scope(
        case(images=[{"id": "photo-1"}]), "请解释照片里的旅游景点", []
    )


def test_photo_report_and_context_followups_do_not_allow_extra_unrelated_tasks():
    record = case(crop="wheat", images=[{"id": "photo-1"}])
    for text in ("请解释这个结果，再说说量子力学", "请回答刚才的问题，再写一首情诗", "先说明排查方向，再推荐一部电影"):
        assert not within_agricultural_scope(record, text, [])



@pytest.mark.parametrize("text", ["黄瓜白粉病怎么用药？", "请说明番茄的病害", "玉米叶片用什么药？"])
def test_new_crop_does_not_reuse_previous_photo_or_product(text, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("an unconfigured provider must not be called")

    monkeypatch.setattr(httpx.AsyncClient, "post", forbidden)
    settings = SimpleNamespace(deepseek_model="deepseek-flash", get_deepseek_key=lambda: "")
    knowledge = Knowledge(ROOT)
    record = case(
        crop="wheat", disease_id="wheat_powdery_mildew", images=[{"id": "prior-wheat-image"}]
    )
    result = asyncio.run(Chat(settings, knowledge).answer(record, text, [], web_search=True))
    assert result["provider"] in {"rules", "knowledge"}
    assert result.get("notice_code") != "crop_mismatch"
    assert result["products"] == []
    assert "小麦白粉病" not in result["text"]
    assert "recognition" not in result
    assert record["crop"] == "wheat" and record["images"]


@pytest.mark.parametrize("text", [
    "小麦和玉米的叶片发黄用什么药？",
    "小麦和黄瓜的叶片发黄用什么药？",
])
def test_explicit_multi_crop_question_does_not_match_case_specific_products(text, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("a multi-crop treatment question cannot use products from one case")

    settings = SimpleNamespace(deepseek_model="deepseek-flash", get_deepseek_key=forbidden)
    knowledge = Knowledge(ROOT)
    monkeypatch.setattr(knowledge, "matching_products", forbidden)
    record = case(crop="wheat", stage="苗期", disease_id="wheat_powdery_mildew")
    result = asyncio.run(Chat(settings, knowledge).answer(record, text, []))
    assert result["provider"] == "rules"
    assert result["products"] == []
