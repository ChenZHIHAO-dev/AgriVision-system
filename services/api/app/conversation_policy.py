"""决定何时附加可跳过的田间信息建议；不负责调用模型或阻塞回答。"""

import re

from .context import STAGES, is_general_question
from .knowledge import CROP_NAMES, query_crop_scope


FIELD_SYMPTOMS = re.compile(
    r"发黄|黄化|黄斑|白斑|斑点|病斑|白粉|枯萎|腐烂|倒伏|长虫|虫卵|缺水|药害|"
    r"叶片有|叶子有|叶面有|叶背有|苗不齐|出苗不齐|烂根|死棵|不长|长势差"
)
FIELD_REFERENCE = re.compile(r"我家|我这|我种|这块田|这株|这片田|本次识别|这次识别|这次照片|这组照片|刚才.*结果|刚刚.*结果|这个结果|这张(?:照片|图片)")
DECLINE_PHOTO = re.compile(r"不拍|不上传|不提供(?:照片|图片)|没有(?:照片|图片)|没(?:有)?法拍|不方便拍|先不(?:拍|传)")


def conversation_scope(text, history):
    """代词追问沿用最近一次用户明确的作物，不从模型回答推断话题。"""
    scope = query_crop_scope(text)
    if scope is not None:
        return scope
    for message in reversed(history):
        if message.get("role") == "user":
            scope = query_crop_scope(message.get("text", ""))
            if scope is not None:
                return scope
    return None


def field_question(case, text):
    """普通农业知识直接解释；明确的田间症状或识别接续才需要个案观察。"""
    if is_general_question(text):
        return False
    if re.search(r"怎么预防|如何预防|如何防治|防治方法|介绍一下|种植方法|种植要点|管理要点", text) and not FIELD_REFERENCE.search(text):
        return False
    photo_followup = case.get("images") and re.search(r"观察|识别|照片|图片|结果|症状", text)
    return bool(FIELD_SYMPTOMS.search(text) or FIELD_REFERENCE.search(text) or photo_followup)


def optional_suggestions(case, text, history):
    """同一字段在本会话只建议一次，已填或主动跳过的字段不再催问。"""
    if case.get("prior_photo_ignored") or not field_question(case, text):
        return {}
    skipped = set(case.get("skipped_context_fields", []))
    suggested = {
        item["context_suggestion"]["field"]
        for item in history
        if item.get("role") == "assistant" and item.get("context_suggestion")
    }
    scope = query_crop_scope(text)
    crop = case.get("crop")
    if not crop and scope and len(scope) == 1:
        crop = next(iter(scope))
    choices = []
    if not crop and scope is None:
        choices.append(("crop", "补充作物名称，可让后续建议更贴合实际；也可以先跳过。",
                        [{"value": value, "label": name} for value, name in CROP_NAMES.items()]))
    if crop in STAGES and case.get("stage") in (None, "", "不清楚"):
        choices.append(("stage", "如果知道生育期，可以补充；不确定也能继续提问。",
                        [{"value": value, "label": value} for value in STAGES[crop]]))
    if not case.get("location"):
        choices.append(("location", "地区会影响后续田间判断，可补充省市，也可以跳过。", []))
    result = {}
    for field, prompt, options in choices:
        if field not in skipped and field not in suggested:
            result["context_suggestion"] = {
                "field": field, "prompt": prompt, "options": options, "optional": True,
            }
            break
    # 拍照是补充证据的入口，不是开启文字问答的前置条件。
    declined = any(
        item.get("role") == "user" and DECLINE_PHOTO.search(item.get("text", ""))
        for item in [*history, {"role": "user", "text": text}]
    )
    photo_already_suggested = any(item.get("photo_suggestion") for item in history)
    if not case.get("images") and not declined and not photo_already_suggested:
        result["photo_suggestion"] = {
            "prompt": "方便时可补一张症状近照和整株照片，帮助核对；也可以继续文字描述。",
            "optional": True,
        }
    return result


def apply_context_choices(case, fields):
    """保存可选资料和跳过选择。重新填写实际值时，解除该字段的跳过状态。"""
    fields = dict(fields)
    skipped = set(case.get("skipped_context_fields", []))
    skipped.update(fields.pop("skip_context_fields", []))
    for field in ("crop", "stage", "location"):
        if fields.get(field) and fields[field] not in ("不清楚", "暂不确定"):
            skipped.discard(field)
    case.update(fields)
    case["skipped_context_fields"] = sorted(skipped)
