from app.evidence import aggregate_images


def record(labels):
    images = []
    versions = []
    for index, label in enumerate(labels, 1):
        disease = (
            label if label not in {"healthy", "wheat_other", "blur", "error"} else None
        )
        status = (
            "needs_retake"
            if label == "blur"
            else "model_error"
            if label == "error"
            else "uncertain"
            if label == "wheat_other"
            else "identified"
        )
        images.append(
            {
                "id": str(index),
                "crop": "wheat",
                "stage": "苗期",
                "quality": {"issues": ["需要对焦"] if label == "blur" else []},
            }
        )
        versions.append(
            {
                "image_id": str(index),
                "crop": "wheat",
                "stage": "苗期",
                "status": status,
                "title": label,
                "disease_id": disease,
                "model_version": "same-version"
                if label not in {"blur", "error"}
                else None,
                "candidates": [{"id": label, "name": label, "score": 0.99}]
                if label not in {"blur", "error"}
                else [],
                "experimental": True,
            }
        )
    return {"images": images, "versions": versions, "crop": "wheat"}


def test_uncertain_last_photo_does_not_erase_supported_earlier_photo():
    result = aggregate_images(record(["wheat_powdery_mildew", "wheat_other"]))
    assert result["disease_id"] == "wheat_powdery_mildew"
    assert result["evidence"]["outcome"] == "partial_support"
    assert result["evidence"]["hypotheses"][0]["image_indices"] == [1]
    assert result["evidence"]["unresolved_images"] == 1
    assert result["candidates"] == []  # no fabricated whole-case probability


def test_different_disease_results_remain_separate_hypotheses():
    result = aggregate_images(
        record(["wheat_powdery_mildew", "wheat_leaf_rust", "wheat_other"])
    )
    assert result["status"] == "uncertain" and result["disease_id"] is None
    assert result["evidence"]["outcome"] == "different_hypotheses"
    assert len(result["evidence"]["hypotheses"]) == 2
    assert (
        result["evidence"]["image_results"][2]["candidates"][0]["id"] == "wheat_other"
    )


def test_multiple_healthy_photos_do_not_vote_down_a_diseased_leaf():
    result = aggregate_images(record(["healthy", "healthy", "wheat_stripe_rust"]))
    assert result["disease_id"] == "wheat_stripe_rust"
    assert result["evidence"]["healthy_reference_images"] == 2


def test_healthy_plus_unknown_does_not_make_the_whole_case_healthy():
    result = aggregate_images(record(["healthy", "wheat_other"]))
    assert result["status"] == "uncertain" and result["disease_id"] is None
    assert result["evidence"]["outcome"] == "outside_supported_scope"


def test_all_blurry_images_return_specific_retake_instructions():
    result = aggregate_images(record(["blur", "blur"]))
    assert result["status"] == "needs_retake"
    assert "需要对焦" in result["evidence"]["next_steps"]


def test_two_supported_images_report_count_without_averaging_scores():
    result = aggregate_images(record(["wheat_leaf_rust", "wheat_leaf_rust"]))
    assert result["evidence"]["outcome"] == "consistent_support"
    assert result["evidence"]["hypotheses"][0]["image_indices"] == [1, 2]
    assert result["candidates"] == []


def test_different_model_versions_are_not_silently_combined():
    case = record(["wheat_leaf_rust", "wheat_leaf_rust"])
    case["versions"][1]["model_version"] = "new-version"
    result = aggregate_images(case)
    assert (
        result["status"] == "uncertain"
        and result["evidence"]["outcome"] == "mixed_model_versions"
    )


def test_later_context_fills_unknown_stage_without_overwriting_known_capture_stage():
    case = record(["wheat_powdery_mildew", "healthy"])
    case["stage"] = "抽穗扬花期"
    case["images"][0]["stage"] = "不清楚"
    case["versions"][0]["stage"] = "不清楚"
    case["images"][1]["stage"] = "苗期"
    result = aggregate_images(case)
    assert result["evidence"]["image_results"][0]["stage"] == "抽穗扬花期"
    assert result["evidence"]["image_results"][1]["stage"] == "苗期"


def test_followup_carries_each_photo_disease_card_to_provider(tmp_path, monkeypatch):
    import asyncio
    import json
    from pathlib import Path
    import httpx
    from app.chat import Chat
    from app.config import Settings
    from app.knowledge import Knowledge

    captured = {}
    async def respond(self, url, **kwargs):
        captured.update(kwargs["json"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "两张照片分别有不同的初步线索，按对应资料核对。"}}]},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.AsyncClient, "post", respond)
    root = Path(__file__).resolve().parents[2]
    settings = Settings(root=root, runtime=tmp_path, models=tmp_path, deepseek_key="test-only-key")
    case = {**record(["wheat_leaf_rust", "wheat_powdery_mildew"]), "location": "", "stage": "不清楚", "note": "", "is_demo": False}
    answer = asyncio.run(Chat(settings, Knowledge(root)).answer(case, "这是什么问题", []))
    assert answer["provider"] == "deepseek"
    context = json.loads(captured["messages"][0]["content"].split("\n", 1)[1])
    assert context["recognition"]["image_count"] == 2
    assert context["recognition"]["disease_id"] is None
    assert context["recognition"]["outcome"] == "different_hypotheses"
    assert context["knowledge_coverage"]["hypothesis_card_ids"] == ["wheat_leaf_rust", "wheat_powdery_mildew"]
    assert context["knowledge_coverage"]["uncovered_hypothesis_ids"] == []
    assert {card["id"] for card in context["knowledge"]} >= {"wheat_leaf_rust", "wheat_powdery_mildew"}
    assert not answer.get("photo_suggestion")


def test_different_clear_photos_do_not_request_the_same_upload_again():
    result = aggregate_images(record(["wheat_leaf_rust", "wheat_stripe_rust"]))
    steps = result["evidence"]["next_steps"]
    assert result["evidence"]["total_images"] == 2
    assert steps and not any("补拍" in step or "上传" in step for step in steps)
    assert "采集位置" in steps[0]


def test_only_failed_photo_is_named_for_retake_in_a_mixed_set():
    result = aggregate_images(record(["wheat_leaf_rust", "wheat_stripe_rust", "blur"]))
    retakes = [step for step in result["evidence"]["next_steps"] if "补拍" in step]
    assert len(retakes) == 1 and "第3张" in retakes[0] and "需要对焦" in retakes[0]


def test_healthy_reference_does_not_require_another_photo():
    result = aggregate_images(record(["healthy"]))
    assert not any("补拍" in step for step in result["evidence"]["next_steps"])
    assert "不能据此排除" in result["evidence"]["summary"]
