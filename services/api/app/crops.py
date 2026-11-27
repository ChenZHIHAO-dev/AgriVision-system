"""业务支持的作物目录；前端也读取同一 JSON，不在各路由重复枚举。

目录只说明可选择的作物和补充信息，不代表模型已经可用。
识别是否开放仍由 ModelRegistry 校验实际模型包决定。
"""
import json
from pathlib import Path
from typing import Literal

CROP_CATALOG = json.loads(
    (Path(__file__).resolve().parents[3] / "knowledge/crops.json").read_text(encoding="utf-8")
)
# Pydantic 会把动态 Literal 展开成 OpenAPI enum，拒绝未支持的病害作物。
Crop = Literal[tuple(CROP_CATALOG)]
CROP_NAMES = {crop: item["name"] for crop, item in CROP_CATALOG.items()}
CROP_ALIASES = {crop: tuple(item["aliases"]) for crop, item in CROP_CATALOG.items()}
STAGES = {crop: item["stages"] for crop, item in CROP_CATALOG.items()}
DEMO_CARDS = {crop: item["demo_card"] for crop, item in CROP_CATALOG.items()}
