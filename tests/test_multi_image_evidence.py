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
