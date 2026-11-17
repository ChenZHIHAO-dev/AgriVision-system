from typing import Literal
from pydantic import BaseModel, Field

Crop = Literal["wheat", "maize", "peanut"]


class DemoRequest(BaseModel):
    crop: Crop = "wheat"


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class CaseUpdate(BaseModel):
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
