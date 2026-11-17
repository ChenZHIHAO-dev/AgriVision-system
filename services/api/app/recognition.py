"""User-facing receipt of vision processing, independent of conversation models."""


def recognition_state(case):
    images = case.get("images") or []
    status = case.get("status", "awaiting_image")
    candidates = case.get("candidates") or []
    result = {
        "context": {
            field: case.get(field, "")
            for field in ("crop", "stage", "location", "variety")
        },
        "image_received": bool(images),
        "image_count": len(images),
        "status": status,
        "outcome": "no_image",
        "summary": "当前是文字咨询，还没有添加症状照片。",
        "model_version": case.get("model_version"),
        "disease_id": case.get("disease_id"),
        "candidates": candidates,
        "experimental": bool(case.get("experimental")),
        "issues": [],
        "next_steps": [],
    }
    if not images:
        if case.get("is_demo"):
            result.update(
                outcome="demo", summary="当前是演示样例，图片与结论只用于演示。"
            )
        return result
    if case.get("evidence"):
        result.update(
            {
                name: case["evidence"][name]
                for name in (
                    "outcome",
                    "summary",
                    "next_steps",
                    "image_results",
                    "hypotheses",
                    "supported_images",
                    "healthy_reference_images",
                    "unresolved_images",
                    "score_policy",
                )
            }
        )
        return result
    steps = [
        "补拍叶片正面、背面和整株照片，保持自然光与清晰对焦",
        "说明症状出现时间、发生范围及近期用药或施肥情况",
    ]
    if status == "identified":
        result.update(
            outcome="supported_result",
            summary="照片已收到，识别模型初步提示："
            + case.get("title", "已取得识别结果")
            + "。",
        )
    elif status == "uncertain":
        other = bool(candidates and candidates[0]["id"] == "wheat_other")
        result.update(
            outcome="outside_supported_scope" if other else "low_confidence",
            summary="照片已收到，当前症状可能不在本版支持范围内，暂不判断具体病害。"
            if other
            else "照片已收到，识别模型暂未达到可靠判断的条件，暂不判断具体病害。",
            next_steps=steps,
        )
    elif status == "needs_retake":
        issues = images[-1].get("quality", {}).get("issues", [])
        result.update(
            outcome="quality_check_failed",
            summary="照片已收到，但画质检查未通过，需要补拍后再识别。",
            issues=issues,
            next_steps=list(dict.fromkeys([*issues, *steps])),
        )
    elif status == "needs_model":
        result.update(
            outcome="model_unavailable",
            summary="照片已保存，当前作物的识别模型尚未就绪。",
            next_steps=["可先描述症状并查阅资料，或切换到已接入模型的作物进行测试"],
        )
    elif status == "model_error":
        result.update(
            outcome="service_error",
            summary="照片已保存，识别服务暂时出错；这不表示没有病害。",
            next_steps=["稍后重试识别，期间可先补充症状描述"],
        )
    else:
        result.update(outcome="pending", summary="照片已收到，识别处理尚未完成。")
    return result
