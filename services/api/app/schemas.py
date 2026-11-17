from typing import Literal
from pydantic import BaseModel, Field

Crop = Literal["wheat", "maize", "peanut"]


class DemoRequest(BaseModel):
    crop: Crop = "wheat"


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    model: Literal["deepseek-flash", "deepseek-v4-pro"] | None = None
    thinking: bool = False
    attachment_ids: list[str] = Field(default_factory=list,max_length=6)
    image_ids: list[str] = Field(default_factory=list,max_length=6)


class ConsultationRequest(BaseModel):
    crop: Crop | None = None
    location: str = Field(default="河南省 / 南阳市", max_length=120)
    stage: str = Field(default="不清楚", max_length=40)
    variety: str = Field(default="", max_length=80)


class CaseUpdate(BaseModel):
    crop: Crop | None = None
    variety: str | None = Field(default=None, max_length=80)
    stage: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=2000)


class Product(BaseModel):
    id: str
    name: str
    registration: str
    ingredient: str
    formulation: str
    crops: list[Crop]
    disease_ids: list[str]
    label_url: str
    instructions: str
    reviewed_by: str
    reviewed_at: str
    valid_until: str
    approved: bool = False
