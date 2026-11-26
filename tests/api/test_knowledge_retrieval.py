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


@pytest.mark.parametrize(("query", "disease_id"), [
    ("小麦颖枯病", "wheat_glume_blotch"),
    ("Parastagonospora nodorum", "wheat_glume_blotch"),
    ("小麦黄矮病毒病", "wheat_barley_yellow_dwarf"),
    ("BYDV", "wheat_barley_yellow_dwarf"),
    ("小麦壳针孢叶枯病", "wheat_septoria_leaf_blotch"),
    ("Zymoseptoria tritici", "wheat_septoria_leaf_blotch"),
])
def test_wheat_disease_names_retrieve_their_own_source_backed_card(knowledge, query, disease_id):
    # 颖枯病与壳针孢叶枯病不是同一病害，旧学名也必须对应正确资料。
    card = knowledge.search(query, "wheat")[0]
    assert card["id"] == disease_id
    advice = knowledge.advice("wheat", disease_id)
    assert advice["sources"] == card["sources"]
    assert advice["sources"]
    assert advice["products"] == []
    assert "识别结果仅供参考" in advice["summary"]
    assert all(source["url"].startswith("https://") for source in advice["sources"])


@pytest.mark.parametrize(("query", "crop", "disease_id"), [
    ("玉米灰斑病", "maize", "maize_gray_leaf_spot"),
    ("gray leaf spot", "maize", "maize_gray_leaf_spot"),
    ("Cercospora zeina", "maize", "maize_gray_leaf_spot"),
    ("花生链格孢叶斑病", "peanut", "peanut_alternaria_leaf_spot"),
    ("Alternaria leaf blight", "peanut", "peanut_alternaria_leaf_spot"),
    ("Alternaria arachidis", "peanut", "peanut_alternaria_leaf_spot"),
])
def test_new_model_labels_retrieve_their_own_card(knowledge, query, crop, disease_id):
    card = knowledge.search(query, crop)[0]
    assert card["id"] == disease_id
    advice = knowledge.advice(crop, disease_id)
    assert advice["summary"] == card["summary"]
    assert advice["actions"] == card["actions"]
    assert advice["sources"] == card["sources"]
    assert advice["products"] == []


@pytest.mark.parametrize("query", ["花生褐斑病", "花生黑斑病"])
def test_alternaria_is_not_an_alias_of_common_peanut_leaf_spot(knowledge, query):
    assert knowledge.search(query, "peanut")[0]["id"] == "peanut_leaf_spot"
    card = knowledge.get("peanut_alternaria_leaf_spot")
    assert not {"褐斑病", "黑斑病"}.intersection(card["keywords"])
    assert "国内没有" not in card["summary"]
    assert any("未取得" in note and "中国" in note for note in card["evidence_limits"])


@pytest.mark.parametrize("disease_id", [
    "wheat_leaf_rust", "maize_gray_leaf_spot", "peanut_alternaria_leaf_spot",
])
def test_management_evidence_has_resolvable_sources_and_region_metadata(knowledge, disease_id):
    card = knowledge.get(disease_id)
    sources = {source["url"]: source for source in card["sources"]}
    assert len(sources) == len(card["sources"])
    assert "识别结果仅供参考" in card["summary"]
    assert card["evidence_limits"] and card["management_evidence"]
    for source in sources.values():
        assert source["title"] and source["publisher"] and source["region"]
        assert source["accessed_at"] and source["url"].startswith("https://")
        assert source["date"] or source["date_note"]
    for evidence in card["management_evidence"]:
        assert evidence["applicability"] and evidence["source_urls"] and evidence["action_indexes"]
        assert set(evidence["source_urls"]).issubset(sources)
        assert all(0 <= index < len(card["actions"]) for index in evidence["action_indexes"])


def test_leaf_rust_supplies_actual_guidance_and_bounded_decision_context(knowledge):
    card = knowledge.search("小麦叶锈病如何防治", "wheat")[0]
    assert card["id"] == "wheat_leaf_rust"
    text = " ".join(knowledge.advice("wheat", card["id"])["actions"])
    # 资料正文包含管理方向，不能又退化为只有补拍/记录/来源链接。
    assert all(term in text for term in ("病叶比例", "抗病品种", "施氮", "戊唑醇", "登记"))
    assert not any("摘除" in action or "带出田外" in action for action in card["actions"])
    limits = " ".join(card["evidence_limits"])
    assert all(term in limits for term in ("自生麦苗", "摘病叶", "喷雾方向", "全国统一"))
    assert "范围小" in text and "不能" in text
