"""Recognize optional context updates without triggering another model answer."""

import re

from .context import STAGES
from .knowledge import CROP_ALIASES, CROP_NAMES


def context_value(text):
    """统一简短资料回复的口语前缀；完整问题不会被当成表单值。"""
    compact = re.sub(r"[\s，,。！!？?、：:]+", "", text)
    compact = re.sub(r"^(?:我|现在|目前|作物|种的|种植的|生育期|是|处于|在)+", "", compact)
    return re.sub(r"(?:阶段|时期|时候)$", "", compact)


def context_reply(text):
    """只识别短资料值或跳过表达，包含新问题的句子交给正常回答流程。"""
    compact = context_value(text)
    values = set(CROP_NAMES.values()) | {"暂不确定", "不确定", "不清楚", "不知道", "先不填", "跳过", "先跳过", "暂不填写", "先不拍", "不拍", "没有照片", "没有图片", "不方便拍照"}
    values.update(alias for aliases in CROP_ALIASES.values() for alias in aliases)
    values.update(stage for stages in STAGES.values() for stage in stages)
    return compact in values


def optional_context_response(case, text, history):
    """简短的资料填写或跳过只确认保存，不自动重答上一问，也不消耗模型请求。"""
    if not context_reply(text) or not any(item.get("role") == "user" for item in history):
        return None
    compact = context_value(text)
    if compact in {"不清楚", "不知道", "不确定", "暂不确定", "先不填", "跳过", "先跳过", "暂不填写"}:
        last = next(
            (item["context_suggestion"] for item in reversed(history) if item.get("context_suggestion")),
            None,
        )
        if last:
            skipped = set(case.get("skipped_context_fields", []))
            skipped.add(last["field"])
            case["skipped_context_fields"] = sorted(skipped)
        reply = "可以先跳过这些资料，直接继续提问。"
    elif re.search(r"不拍|没有(?:照片|图片)|不方便拍", compact):
        reply = "可以继续用文字描述，不需要上传照片。"
    else:
        reply = "已记录补充信息，你可以继续提问。"
    return {"provider": "rules", "text": reply, "sources": [], "products": [], "thinking": False}
