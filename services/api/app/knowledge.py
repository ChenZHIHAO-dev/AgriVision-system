import json
import re
from datetime import date
from pathlib import Path

from .schemas import Product

CROP_NAMES = {"wheat": "小麦", "maize": "玉米", "peanut": "花生"}


def tokens(text: str):
    text = re.sub(r"\s+", "", text.lower())
    return set(text[i:i + 2] for i in range(max(0, len(text) - 1)))


class Knowledge:
    def __init__(self, root: Path):
        self.cards = json.loads((root / "knowledge/cards.json").read_text(encoding="utf-8"))
        self.products = []
        path = root / "knowledge/products.json"
        for raw in json.loads(path.read_text(encoding="utf-8")) if path.exists() else []:
            self.products.append(Product.model_validate(raw))

    def search(self, query="", crop=None, limit=50):
        cards = [c for c in self.cards if not crop or c["crop"] in (crop, "general")]
        if not query.strip():
            return cards[:limit]
        query_tokens = tokens(query)
        ranked = []
        for card in cards:
            material = card["title"] + " ".join(card["keywords"]) + card["summary"]
            score = len(query_tokens & tokens(material))
            score += 12 if card["title"] in query or any(k in query for k in card["keywords"] if len(k) >= 3) else 0
            if score:
                ranked.append((score, card))
        return [card for _, card in sorted(ranked, key=lambda x: x[0], reverse=True)[:limit]]

    def get(self, card_id):
        return next((c for c in self.cards if c["id"] == card_id), None)

    def matching_products(self, crop, disease_id, stage=""):
        # Only reviewed, unexpired label records can become user-facing products.
        if not disease_id:
            return []
        today = date.today().isoformat()
        return [p.model_dump() for p in self.products if (
            p.approved and p.reviewed_by and p.reviewed_at and p.registration
            and p.label_url.startswith("https://") and p.instructions
            and p.valid_until >= today and crop in p.crops and disease_id in p.disease_ids
        )]

    def advice(self, crop, disease_id, demo=False, stage=""):
        card = self.get(disease_id) if disease_id else None
        if card is None:
            return {
                "summary": "先补充作物症状与拍摄信息，建立这次问诊的判断依据。",
                "actions": ["补一张症状近照和一张整株照片", "记录出现时间、田间分布及近期用药", "可以继续咨询已收录的病虫害资料"],
                "sources": [], "products": [],
            }
        return {
            "summary": ("这是演示样例的资料说明。" if demo else "") + card["summary"],
            "actions": card["actions"],
            "sources": card["sources"],
            "products": [] if demo else self.matching_products(crop, disease_id, stage),
        }
