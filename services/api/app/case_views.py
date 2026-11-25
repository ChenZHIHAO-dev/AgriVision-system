"""Public observation record and image-only transcript formatting."""

from datetime import UTC, datetime

from .recognition import recognition_state


def now():
    return datetime.now(UTC).isoformat()


def case_advice(case, receipt, knowledge):
    advice = knowledge.advice(
        case["crop"], case.get("disease_id"), case["is_demo"], case["stage"]
    )
    if receipt["image_received"] and case["status"] != "identified":
        advice["summary"] = receipt["summary"]
        advice["actions"] = receipt["next_steps"] or advice["actions"]
    if receipt.get("outcome") == "different_hypotheses":
        sources = {}
        for hypothesis in receipt.get("hypotheses", []):
            card = knowledge.get(hypothesis["disease_id"])
            for source in card["sources"] if card else []:
                sources[source["url"]] = source
        advice["sources"] = list(sources.values())
    return advice

def serialize_case(case, *, store, auth, knowledge):
    result = dict(case)
    record_owner = store.owner_of(case["id"])
    result["persistence"] = (
        "temporary" if record_owner and record_owner.startswith("g_") else "account"
    )
    result["images"] = [
        {
            **image,
            "url": f"/api/cases/{case['id']}/images/{image['id']}?access_token="
            + auth.image_token(record_owner, case["id"], image["id"]),
        }
        for image in case["images"]
    ]
    result["recognition"] = recognition_state(case)
    result["documents"] = [
        {key: value for key, value in document.items() if key != "text"}
        for document in case.get("documents", [])
    ]
    result["advice"] = case_advice(case, result["recognition"], knowledge)
    result["messages"] = store.messages(case["id"])
    return result

def seed_photo_transcript(case, *, store, knowledge):
    receipt = recognition_state(case)
    advice = case_advice(case, receipt, knowledge)
    assistant = {
        "role": "assistant",
        "provider": "recognition",
        "created_at": now(),
        "text": "### 识别参考\n\n"
        + receipt["summary"]
        + "\n\n### 观察建议\n\n"
        + "\n".join("- " + action for action in advice["actions"][:3])
        + "\n\n如需进一步排查或了解处理方法，可以继续提问。",
        "sources": advice["sources"],
        "products": [],
        "thinking": False,
        "recognition": receipt,
    }
    user_message = {
        "role": "user",
        "provider": "photo",
        "created_at": now(),
        "text": "上传了一张" + case["crop_name"] + "照片",
        "sources": [],
        "products": [],
        "attachments": [
            {"id": case["images"][0]["id"], "name": "症状照片", "kind": "image"}
        ],
    }
    store.add_exchange(case["id"], user_message, assistant)
