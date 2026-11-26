import asyncio
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import zipfile

import httpx
from fastapi.testclient import TestClient
import pytest

from app.attachments import extract_document
from app.chat import Chat
from app.config import Settings
from app.knowledge import Knowledge
from app.application import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_local_reply_does_not_repeat_a_known_growth_stage(tmp_path):
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path)
    case = {
        "crop": "wheat",
        "stage": "拔节孕穗期",
        "status": "awaiting_image",
        "is_demo": False,
        "note": "",
        "location": "南阳",
        "disease_id": None,
    }
    result = asyncio.run(
        Chat(settings, Knowledge(ROOT)).answer(case, "叶片疑似条锈病，先观察什么？", [])
    )
    assert result["provider"] == "knowledge"
    assert "哪个生育期" not in result["text"]


def test_quoted_mock_secret_loads_only_in_runtime_and_repr_hides_it(tmp_path):
    mock = tmp_path / "mock-secret.env"
    mock.write_text('DEEPSEEK_API_KEY="test-only-provider-token"\n', encoding="utf-8")
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path, secret_file=mock)
    assert settings.get_deepseek_key() == "test-only-provider-token"
    assert "sk-only" not in repr(
        replace(settings, deepseek_key="test-only-provider-token")
    )


@pytest.mark.parametrize(
    "model,thinking", [("deepseek-flash", False), ("deepseek-v4-pro", True)]
)
def test_provider_receives_text_context_and_mode_without_any_image(
    model, thinking, tmp_path, monkeypatch
):
    seen = {}

    async def respond(self, url, **kwargs):
        seen.update(kwargs)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "先记录症状出现时间，观察叶片两面和田间分布。"
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", respond)
    settings = Settings(
        root=ROOT,
        runtime=tmp_path,
        models=tmp_path,
        deepseek_key="fake-test-credential",
    )
    case = {
        "crop": "wheat",
        "location": "南阳",
        "stage": "拔节孕穗期",
        "note": "零星发生",
        "status": "identified",
        "is_demo": False,
        "title": "疑似小麦条锈病",
        "disease_id": "wheat_stripe_rust",
        "model_version": "test-cnn",
        "images": [{"url": "data:image/jpeg;base64,NEVER_FORWARD"}],
        "documents": [
            {
                "id": "doc",
                "name": "农事记录.txt",
                "text": "田间发现零星黄斑，前日有降雨。",
            }
        ],
    }
    result = asyncio.run(
        Chat(settings, Knowledge(ROOT)).answer(
            case, "需要补充什么信息？", [], model, thinking
        )
    )
    assert (
        result["provider"] == "deepseek"
        and result["model"] == model
        and result["thinking"] == thinking
    )
    assert seen["json"]["thinking"]["type"] == ("enabled" if thinking else "disabled")
    assert seen["json"]["model"] == model
    payload = json.dumps(seen["json"], ensure_ascii=False)
    assert "test-cnn" in payload and "农事记录.txt" in payload
    assert "data:image" not in payload and "NEVER_FORWARD" not in payload
    assert (
        "fake-test-credential" not in payload
        and "fake-test-credential" not in json.dumps(result)
    )


def test_provider_cannot_echo_credential_to_client(tmp_path, monkeypatch):
    async def respond(self, url, **kwargs):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "fake-secret-do-not-return"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", respond)
    settings = Settings(
        root=ROOT,
        runtime=tmp_path,
        models=tmp_path,
        deepseek_key="fake-secret-do-not-return",
    )
    case = {
        "crop": "wheat",
        "location": "南阳",
        "stage": "苗期",
        "note": "",
        "status": "awaiting_image",
        "is_demo": False,
        "title": "咨询",
        "disease_id": None,
    }
    result = asyncio.run(
        Chat(settings, Knowledge(ROOT)).answer(case, "需要拍哪些照片？", [])
    )
    assert (
        result["provider"] == "knowledge"
        and result["notice_code"] == "unverified_response"
    )
    assert "fake-secret-do-not-return" not in json.dumps(result)


def test_general_questions_do_not_require_crop_or_stage(tmp_path, account_headers, admin_hash):
    settings = Settings(
        root=ROOT, runtime=tmp_path / "runtime", models=tmp_path / "models", admin_password_hash=admin_hash
    )
    with TestClient(create_app(settings)) as client:
        owner = account_headers(client)
        case = client.post("/api/consultations", headers=owner, json={}).json()
        path = f"/api/cases/{case['id']}"
        for text in ("如何拍清楚症状？", "怎么看农药标签？", "生育期是什么意思？"):
            answer = client.post(
                path + "/messages", headers=owner, json={"text": text}
            ).json()
            assert answer["provider"] in ("knowledge", "rules")
            assert "follow_up" not in answer
        case = client.get(path, headers=owner).json()
        assert case["crop"] is None
        assert "pending_question" not in case
        field_question = client.post(
            path + "/messages",
            headers=owner,
            json={"text": "我这块田的叶片有白斑，怎么处理？"},
        ).json()
        assert field_question["follow_up"]["field"] == "crop"


def test_text_consultation_collects_context_with_choice_cards(tmp_path, account_headers, admin_hash):
    settings = Settings(
        root=ROOT, runtime=tmp_path / "runtime", models=tmp_path / "models", admin_password_hash=admin_hash
    )
    with TestClient(create_app(settings)) as client:
        owner = account_headers(client)
        case = client.post("/api/consultations", headers=owner, json={}).json()
        assert case["crop"] is None and case["images"] == []
        path = f"/api/cases/{case['id']}"
        first = client.post(
            path + "/messages",
            headers=owner,
            json={"text": "叶片上有黄斑，应该怎么观察？"},
        ).json()
        assert (
            first["provider"] == "clarification"
            and first["follow_up"]["field"] == "crop"
        )
        assert (
            client.post(
                path + "/context", headers=owner, json={"crop": "wheat"}
            ).json()["crop_name"]
            == "小麦"
        )
        second = client.post(
            path + "/messages", headers=owner, json={"text": "是小麦。"}
        ).json()
        assert second["follow_up"]["field"] == "stage"
        client.post(path + "/context", headers=owner, json={"stage": "拔节孕穗期"})
        final = client.post(
            path + "/messages", headers=owner, json={"text": "接着说说检查方法。"}
        ).json()
        assert "follow_up" not in final
        assert (
            client.post(
                path + "/messages",
                headers=owner,
                json={"text": "问题", "model": "not-allowed"},
            ).status_code
            == 422
        )


def test_document_ownership_extraction_and_removal(tmp_path, account_headers, admin_hash):
    settings = Settings(
        root=ROOT, runtime=tmp_path / "runtime", models=tmp_path / "models", admin_password_hash=admin_hash
    )
    with TestClient(create_app(settings)) as client:
        owner = account_headers(client)
        other = {"X-Client-ID": "other-test-guest"}
        case = client.post(
            "/api/consultations", headers=owner, json={"crop": "wheat", "stage": "苗期"}
        ).json()
        path = f"/api/cases/{case['id']}"
        result = client.post(
            path + "/attachments",
            headers=owner,
            data={"filename": "田间记录.txt"},
            files={
                "file": (
                    "blob",
                    "小麦田间记录：叶片零星黄斑，昨天有降雨。".encode("utf-8"),
                    "text/plain",
                )
            },
        )
        assert result.status_code == 201
        document = result.json()["documents"][0]
        assert document["characters"] > 0 and "text" not in document
        answer = client.post(
            path + "/messages",
            headers=owner,
            json={"text": "请根据资料说明", "attachment_ids": [document["id"]]},
        ).json()
        assert "田间记录.txt" in answer["text"]
        assert (
            client.post(
                path + "/messages",
                headers=owner,
                json={"text": "问题", "attachment_ids": ["foreign-id"]},
            ).status_code
            == 422
        )
        assert (
            client.delete(
                path + "/attachments/" + document["id"], headers=other
            ).status_code
            == 401
        )
        assert (
            client.delete(
                path + "/attachments/" + document["id"], headers=owner
            ).status_code
            == 204
        )
        assert client.get(path, headers=owner).json()["documents"] == []


def test_document_parser_handles_docx_and_rejects_secrets_or_empty_pdf():
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>田间</w:t></w:r><w:r><w:t>观察记录</w:t></w:r></w:p><w:p><w:r><w:t>小麦苗期</w:t></w:r></w:p></w:body></w:document>',
        )
    assert (
        extract_document("记录.docx", stream.getvalue())["text"]
        == "田间观察记录\n小麦苗期"
    )
    with pytest.raises(ValueError, match="密钥"):
        extract_document(
            "不要上传.txt", b'DEEPSEEK_API_KEY="test-only-provider-token"'
        )
    from pypdf import PdfWriter

    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)
    with pytest.raises(ValueError, match="OCR"):
        extract_document("scan.pdf", output.getvalue())


@pytest.mark.parametrize("has_document", [False, True])
@pytest.mark.parametrize("provider_fails", [False, True])
def test_local_fallback_cites_only_material_used(tmp_path, monkeypatch, has_document, provider_fails):
    async def fail(*args, **kwargs):
        raise httpx.ConnectError("unavailable")

    monkeypatch.setattr(httpx.AsyncClient, "post", fail)
    settings = Settings(
        root=ROOT, runtime=tmp_path, models=tmp_path,
        deepseek_key="fake-test-key" if provider_fails else "",
    )
    case = {
        "crop": "wheat",
        "location": "南阳",
        "stage": "苗期",
        "is_demo": False,
        "note": "",
        "status": "uncertain",
        "images": [{"id": "image"}],
        "candidates": [],
        "documents": [{"name": "田间记录.txt", "text": "前日降雨，叶片零星黄化。"}]
        if has_document else [],
    }
    result = asyncio.run(
        Chat(settings, Knowledge(ROOT)).answer(case, "小麦条锈病的田间观察要点？", [])
    )
    assert result["provider"] == "knowledge"
    assert "照片已收到" in result["text"]
    assert result["sources"] == []
    if has_document:
        assert "田间记录.txt" in result["text"] and "前日降雨" in result["text"]
    else:
        assert "补拍" in result["text"]


@pytest.mark.parametrize("disease_id,name", [
    ("wheat_glume_blotch", "小麦颖枯病"),
    ("wheat_barley_yellow_dwarf", "小麦黄矮病"),
    ("wheat_septoria_leaf_blotch", "小麦壳针孢叶枯病"),
])
def test_new_recognition_without_knowledge_card_does_not_borrow_another_disease(tmp_path, disease_id, name):
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path)
    case = {
        "crop": "wheat", "stage": "苗期", "location": "", "note": "", "is_demo": False,
        "status": "identified", "disease_id": disease_id, "title": "疑似" + name,
        "images": [{"id": "photo"}], "candidates": [{"id": disease_id, "name": name}],
    }
    knowledge = Knowledge(ROOT)
    # Exercise a genuine coverage gap even after the bundled library gains this card.
    knowledge.cards = [card for card in knowledge.cards if card["id"] != disease_id]
    result = asyncio.run(Chat(settings, knowledge).answer(
        case, "叶片上像撒了一层白粉，需要怎样观察？", []
    ))
    assert result["notice_code"] == "not_configured"
    assert name in result["text"]
    assert "尚未覆盖" in result["text"]
    assert "白粉病" not in result["text"]
    assert result["sources"] == []


def test_general_concept_can_use_other_disease_card_without_changing_recognition(tmp_path):
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path)
    case = {
        "crop": "wheat", "stage": "苗期", "location": "", "note": "", "is_demo": False,
        "status": "identified", "disease_id": "wheat_glume_blotch", "title": "疑似小麦颖枯病",
        "images": [{"id": "photo"}], "candidates": [],
    }
    result = asyncio.run(Chat(settings, Knowledge(ROOT)).answer(case, "什么是小麦白粉病？", []))
    assert "小麦白粉病" in result["text"]
    assert result["sources"]
    assert case["disease_id"] == "wheat_glume_blotch"


def test_provider_receives_explicit_knowledge_gap_and_no_assumed_region(tmp_path, monkeypatch):
    seen = {}

    async def respond(_self, url, **kwargs):
        seen.update(kwargs["json"])
        return httpx.Response(200, json={"choices": [{"message": {
            "content": "模型初步提示疑似小麦颖枯病，目前还缺少对应审核资料。"
        }}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", respond)
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path, deepseek_key="fake-coverage-test")
    case = {
        "crop": "wheat", "stage": "苗期", "location": "", "note": "", "is_demo": False,
        "status": "identified", "disease_id": "wheat_glume_blotch", "title": "疑似小麦颖枯病",
        "images": [{"id": "photo"}], "candidates": [],
    }
    knowledge = Knowledge(ROOT)
    knowledge.cards = [card for card in knowledge.cards if card["id"] != "wheat_glume_blotch"]
    result = asyncio.run(Chat(settings, knowledge).answer(
        case, "叶片上像撒了一层白粉，需要怎样观察？", []
    ))
    assert result["provider"] == "deepseek"
    system = seen["messages"][0]["content"]
    context = json.loads(system.rsplit("\n", 1)[-1])
    assert context["knowledge"] == []
    assert context["knowledge_coverage"] == {
        "recognized_disease_id": "wheat_glume_blotch",
        "recognized_disease_card_available": False,
        "retrieved_card_ids": [],
    }
    assert context["location"] == ""
    assert "服务河南南阳及周边" not in system
    assert result["sources"] == []


@pytest.mark.parametrize("disease_id", [
    "wheat_glume_blotch",
    "wheat_barley_yellow_dwarf",
    "wheat_septoria_leaf_blotch",
])
def test_new_wheat_recognition_sends_matched_evidence_to_provider(tmp_path, monkeypatch, disease_id):
    seen = {}

    async def respond(_self, url, **kwargs):
        seen.update(kwargs["json"])
        return httpx.Response(200, json={"choices": [{"message": {
            "content": "这是本次识别的初步线索，请对照资料核对田间表现。"
        }}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", respond)
    settings = Settings(root=ROOT, runtime=tmp_path, models=tmp_path, deepseek_key="fake-card-test")
    knowledge = Knowledge(ROOT)
    card = knowledge.get(disease_id)
    case = {
        "crop": "wheat", "stage": "暂不确定", "location": "", "note": "", "is_demo": False,
        "status": "identified", "disease_id": disease_id, "title": "疑似" + card["title"],
        "images": [{"id": "photo"}], "candidates": [{"id": disease_id, "name": card["title"]}],
    }
    result = asyncio.run(Chat(settings, knowledge).answer(case, "请说明本次识别结果", []))
    assert result["provider"] == "deepseek"
    context = json.loads(seen["messages"][0]["content"].rsplit("\n", 1)[-1])
    assert context["knowledge_coverage"]["recognized_disease_card_available"] is True
    assert context["knowledge"][0]["id"] == disease_id
    assert context["knowledge"][0]["sources"] == card["sources"]
    assert all(source in result["sources"] for source in card["sources"])
    assert result["products"] == []
