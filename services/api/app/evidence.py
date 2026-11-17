"""Summarize per-image evidence without averaging classification probabilities."""


def aggregate_images(case):
    images = case.get("images") or []
    if not images:
        return {}
    versions = {
        item["image_id"]: item
        for item in case.get("versions", [])
        if item.get("image_id")
    }
    results = []
    for index, image in enumerate(images, 1):
        image_id = image.get("id", f"legacy-{index}")
        prediction = versions.get(image_id)
        if prediction is None:
            prediction = case if len(images) == 1 else {}
        candidates = prediction.get("candidates") or []
        results.append(
            {
                "image_id": image_id,
                "image_index": index,
                "crop": image.get("crop") or prediction.get("crop") or case.get("crop"),
                "stage": next(
                    (
                        stage
                        for stage in (
                            image.get("stage"),
                            prediction.get("stage"),
                            case.get("stage"),
                        )
                        if stage and stage != "不清楚"
                    ),
                    case.get("stage", "不清楚"),
                ),
                "status": prediction.get("status", "pending"),
                "title": prediction.get("title", "历史图片尚缺独立识别记录"),
                "disease_id": prediction.get("disease_id"),
                "candidates": candidates[:3],
                "model_version": prediction.get("model_version"),
                "experimental": bool(prediction.get("experimental")),
                "quality_issues": image.get("quality", {}).get("issues", []),
            }
        )
    model_versions = sorted(
        {item["model_version"] for item in results if item["model_version"]}
    )
    supported = [
        item
        for item in results
        if item["status"] == "identified" and item["disease_id"]
    ]
    healthy = [
        item
        for item in results
        if item["status"] == "identified"
        and not item["disease_id"]
        and item["candidates"]
        and item["candidates"][0]["id"] == "healthy"
    ]
    unresolved = [
        item for item in results if item not in supported and item not in healthy
    ]
    hypotheses = {}
    for item in supported:
        entry = hypotheses.setdefault(
            item["disease_id"],
            {
                "disease_id": item["disease_id"],
                "name": item["candidates"][0]["name"]
                if item["candidates"]
                else item["title"].removeprefix("疑似"),
                "image_indices": [],
            },
        )
        entry["image_indices"].append(item["image_index"])
    steps = [
        "补拍有症状叶片的正面、背面与整株照片",
        "补充症状出现时间、田间分布和近期施药或施肥情况",
    ]
    disease_id = None
    if len({item["crop"] for item in results}) > 1:
        status, outcome = "uncertain", "mixed_crops"
        title = "照片包含不同作物，请分开问诊"
        summary = "照片已收到，但存在不同作物记录，不能把它们合并判断。"
        steps = ["按作物分别新建问诊，保留各自的种植情况"]
    elif len(model_versions) > 1:
        status, outcome = "uncertain", "mixed_model_versions"
        title = "照片使用了不同版本模型，需要统一核对"
        summary = "照片已收到，各张识别使用的模型版本不同，暂不合并结论。"
        steps = ["使用同一版本模型重新识别后再比较，原始结果继续保留"]
    elif len(hypotheses) > 1:
        status, outcome = "uncertain", "different_hypotheses"
        title = "不同照片提示不同病害，需要进一步核对"
        summary = (
            "照片已收到。"
            + "；".join(
                "第"
                + "、".join(map(str, item["image_indices"]))
                + "张提示疑似"
                + item["name"]
                for item in hypotheses.values()
            )
            + "。这些是不同照片的初步线索，不自动选取一种病害。"
        )
        steps = ["确认这些照片是否来自同一株或同一块田，混拍时请分开问诊", *steps]
    elif hypotheses:
        hypothesis = next(iter(hypotheses.values()))
        disease_id = hypothesis["disease_id"]
        status = "identified"
        outcome = "partial_support" if unresolved or healthy else "consistent_support"
        title = "疑似" + hypothesis["name"]
        summary = (
            "照片已收到。第"
            + "、".join(map(str, hypothesis["image_indices"]))
            + "张的识别模型初步提示疑似"
            + hypothesis["name"]
            + "。"
        )
        if healthy:
            summary += f"另有 {len(healthy)} 张未见已支持病害的明显特征。"
        if unresolved:
            summary += (
                f"仍有 {len(unresolved)} 张未判明或需要补拍，不能代表整组均已确认。"
            )
        steps = []
    elif healthy and not unresolved:
        status, outcome = "identified", "healthy_reference"
        title = "已处理照片未见已支持病害的明显特征"
        summary = f"照片已收到。{len(healthy)} 张照片未见本版已支持病害的明显特征，不能据此排除其他病害或非病害原因。"
    else:
        statuses = {item["status"] for item in results}
        if statuses == {"needs_retake"}:
            status, outcome, title = (
                "needs_retake",
                "quality_check_failed",
                "需要更清晰的症状照片",
            )
            summary = "照片已收到，但画质检查未通过，需要补拍后再识别。"
            steps = list(
                dict.fromkeys(
                    [reason for item in results for reason in item["quality_issues"]]
                    + steps
                )
            )
        elif statuses == {"needs_model"}:
            status, outcome, title = (
                "needs_model",
                "model_unavailable",
                "当前作物的识别模型尚未就绪",
            )
            summary = "照片已保存，当前作物还没有可用的识别模型。"
            steps = ["可先描述症状并查阅资料，或使用已接入模型的作物进行测试"]
        elif statuses == {"model_error"}:
            status, outcome, title = (
                "model_error",
                "service_error",
                "本次识别服务暂时出错",
            )
            summary = "照片已保存，识别服务暂时出错；这不表示没有病害。"
            steps = ["稍后重试识别，期间可先补充症状描述"]
        else:
            other = any(
                item["candidates"] and item["candidates"][0]["id"] == "wheat_other"
                for item in unresolved
            )
            status, outcome, title = (
                "uncertain",
                "outside_supported_scope" if other else "low_confidence",
                "暂未形成可靠的病害判断",
            )
            summary = (
                "照片已收到，当前症状可能不在本版支持范围内，暂不判断具体病害。"
                if other
                else "照片已收到，目前还没有可靠的病害判断，请结合逐张回执继续核对。"
            )
            if healthy:
                summary += f"其中 {len(healthy)} 张未见已支持病害特征，其余照片仍待判断，不能把整组判为健康。"
    evidence = {
        "outcome": outcome,
        "summary": summary,
        "total_images": len(results),
        "supported_images": len(supported),
        "healthy_reference_images": len(healthy),
        "unresolved_images": len(unresolved),
        "hypotheses": list(hypotheses.values()),
        "image_results": results,
        "next_steps": steps,
        "score_policy": "per-image-only; no probability averaging or majority vote",
    }
    return {
        "status": status,
        "title": title,
        "disease_id": disease_id,
        "candidates": results[0]["candidates"] if len(results) == 1 else [],
        "model_version": model_versions[0] if len(model_versions) == 1 else None,
        "experimental": any(item["experimental"] for item in results),
        "evidence": evidence,
    }
