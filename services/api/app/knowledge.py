import json
import re
from datetime import date
from pathlib import Path

from .schemas import Product

from .crops import CROP_NAMES, CROP_ALIASES

CROPS_OUTSIDE_LIBRARY = (
    "水稻", "稻谷", "大豆", "油菜",
    "辣椒", "白菜", "马铃薯", "土豆", "西瓜", "棉花", "大麦", "高粱",
)
CONTEXT_WORDS = (
    "叶片", "叶面", "叶子", "麦叶", "症状", "病害", "田间", "地块", "作物",
    "情况", "颜色", "部位", "出现", "查看", "观察", "判断", "需要", "什么",
    "怎么", "如何", "时间", "近期", "当地", "南阳", "生育期", "抽穗扬花",
)
CONTEXT_KEYWORDS = {"抽穗", "扬花", "麦穗", "虫子"}


def query_crop_scope(query: str) -> frozenset[str] | None:
    """Identify named crops, including crops without indexed cards."""
    compact = re.sub(r"\s+", "", query)
    supported = frozenset(
        crop
        for crop, label in CROP_NAMES.items()
        if label in compact or any(alias in compact for alias in CROP_ALIASES.get(crop, ()))
    )
    outside = frozenset(label for label in CROPS_OUTSIDE_LIBRARY if label in compact)
    return (supported | outside) or None



def crop_scope_conflicts(crop: str | None, scope: frozenset[str] | None) -> bool:
    return crop in CROP_NAMES and scope is not None and crop not in scope


def tokens(text: str):
    text = re.sub(r"\s+", "", text.lower())
    return set(text[i:i + 2] for i in range(max(0, len(text) - 1)))


CONTEXT_TOKENS = set().union(
    *(tokens(word) for word in (
        *CONTEXT_WORDS, *CONTEXT_KEYWORDS, *CROP_NAMES.values(), *CROPS_OUTSIDE_LIBRARY,
    )),
    *(tokens(alias) for aliases in CROP_ALIASES.values() for alias in aliases),
)


class Knowledge:
    def __init__(self, root: Path):
        self.cards = json.loads((root / "knowledge/cards.json").read_text(encoding="utf-8"))
        self.products = []
        path = root / "knowledge/products.json"
        for raw in json.loads(path.read_text(encoding="utf-8")) if path.exists() else []:
            self.products.append(Product.model_validate(raw))

    def search(self, query="", crop=None, limit=50):
        scope = query_crop_scope(query)
        if scope is None and crop:
            scope = frozenset({crop})
        cards = [
            card for card in self.cards
            if scope is None or card["crop"] == "general" or card["crop"] in scope
        ]
        if not query.strip():
            return cards[:limit]

        general_only = scope is not None and scope.isdisjoint(CROP_NAMES)
        query = query.lower()
        query_tokens = tokens(query) - CONTEXT_TOKENS
        ranked = []
        for card in cards:
            title_match = card["title"].lower() in query
            keyword_match = any(
                keyword.lower() in query
                for keyword in card["keywords"]
                if keyword not in CONTEXT_KEYWORDS
            )
            fields = (card["title"], *card["keywords"], card["summary"])
            card_tokens = set().union(*(tokens(field) for field in fields))
            overlap = len(query_tokens & card_tokens)
            # A crop or an isolated bigram is not enough to ground a recommendation.
            if title_match or keyword_match or (not general_only and overlap >= 2):
                ranked.append(((title_match, keyword_match, overlap), card))
        ranked.sort(key=lambda row: row[0], reverse=True)
        return [card for _, card in ranked[:limit]]

    def get(self, card_id):
        return next((c for c in self.cards if c["id"] == card_id), None)

    def recognition_cards(self, case):
        """逐个匹配已识别线索的资料；不同照片的病名不能合并或靠关键词丢掉。

        只取服务端已处理的 hypotheses，不把低分 top-k 全部当成病害。
        没有资料的病名由调用方明确报告缺口，不借其他病害资料填充。
        """
        ids = [item["disease_id"] for item in case.get("evidence", {}).get("hypotheses", [])]
        if case.get("disease_id"):
            ids.insert(0, case["disease_id"])
        return [
            card for identifier in dict.fromkeys(ids)
            if (card := self.get(identifier)) and card["crop"] == case.get("crop")
        ]

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
        if card is None or card["crop"] not in (crop, "general"):
            return {
                "summary": "补充作物症状和拍摄信息，便于在这条记录中核对观察线索。",
                "actions": ["补一张症状近照和一张整株照片", "记录出现时间、田间分布及近期用药", "可以向 AI 询问相关病虫害资料"],
                "sources": [], "products": [],
            }
        return {
            "summary": ("这是演示样例的资料说明。" if demo else "") + card["summary"],
            "actions": card["actions"],
            "sources": card["sources"],
            "products": [] if demo else self.matching_products(crop, disease_id, stage),
        }
