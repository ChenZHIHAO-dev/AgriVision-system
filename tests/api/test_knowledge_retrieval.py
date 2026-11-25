from pathlib import Path

import pytest

from app.knowledge import Knowledge


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def knowledge():
    return Knowledge(ROOT)


@pytest.mark.parametrize("context", [None, "wheat"])
@pytest.mark.parametrize("query", ["黄瓜霜霉病叶片症状", "番茄白粉病的叶片表现", "西红柿叶片有哪些病斑"])
def test_unindexed_crop_does_not_retrieve_unrelated_crop_cards(knowledge, query, context):
    assert knowledge.search(query, context) == []


def test_unindexed_crop_can_retrieve_relevant_general_guide(knowledge):
    cards = knowledge.search("黄瓜病叶怎么拍照？", "wheat")
    assert [card["id"] for card in cards] == ["photo_guide"]


@pytest.mark.parametrize("context", [None, "wheat"])
def test_named_supported_crop_controls_query_scope(knowledge, context):
    cards = knowledge.search("玉米叶片锈斑怎么判断？", context)
    assert cards[0]["crop"] == "maize"
    assert all(card["crop"] in {"maize", "general"} for card in cards)


def test_unnamed_crop_keeps_existing_case_filter_and_known_disease(knowledge):
    assert all(
        card["crop"] in {"peanut", "general"}
        for card in knowledge.search("", "peanut")
    )
    assert knowledge.search("条锈病如何区分？")[0]["id"] == "wheat_stripe_rust"



def test_named_crop_comparison_can_retrieve_both_scopes(knowledge):
    cards = knowledge.search("小麦和玉米的叶片锈斑有什么区别？", "peanut")
    assert {card["crop"] for card in cards if card["crop"] != "general"} == {"wheat", "maize"}


@pytest.mark.parametrize("query", [
    "南阳小麦最近几天会下雨吗？",
    "小麦滴灌管的过滤网怎么清洗？",
    "叶子颜色有点不对，应该怎么判断？",
    "麦穗什么时候抽穗扬花？",
])
def test_crop_and_generic_field_language_do_not_supply_disease_evidence(knowledge, query):
    assert knowledge.search(query, "wheat") == []


@pytest.mark.parametrize(("query", "expected"), [
    ("叶片黄色小粉疱顺叶脉长成一条一条", "wheat_stripe_rust"),
    ("叶子上是散着的红褐色小点，怎么分辨", "wheat_leaf_rust"),
    ("麦叶上像撒了一层白面，茂密的地方更多", "wheat_powdery_mildew"),
    ("麦子上有白粉", "wheat_powdery_mildew"),
])
def test_specific_symptoms_and_short_aliases_still_find_relevant_cards(knowledge, query, expected):
    assert knowledge.search(query, "wheat")[0]["id"] == expected
