"""Keep a real user question while the program collects missing context."""

import re
import uuid

from .context import STAGES
from .knowledge import CROP_ALIASES, CROP_NAMES


def context_reply(text):
    """Only short, explicit field answers continue intake; a new question supersedes it."""
    compact = re.sub(r"[\s，。！!、：:]+", "", text)
    compact = re.sub(r"^(?:现在|目前|作物|种的|种植的|生育期|是|处于|在)+", "", compact)
    compact = re.sub(r"(?:阶段|时期|时候)$", "", compact)
    values = set(CROP_NAMES.values()) | {"暂不确定", "不确定", "不清楚", "不知道"}
    values.update(alias for aliases in CROP_ALIASES.values() for alias in aliases)
    values.update(stage for stages in STAGES.values() for stage in stages)
    return compact in values


def pending_question(text, body):
    return {
        "id": uuid.uuid4().hex,
        "text": text,
        "model": body.model,
        "thinking": body.thinking,
        "web_search": body.web_search,
        "attachment_ids": body.attachment_ids,
        "image_ids": body.image_ids,
    }
