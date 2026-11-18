from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Crop = Literal["wheat", "maize", "peanut"]


class DemoRequest(BaseModel):
    crop: Crop = "wheat"


class ResumeRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=80)
    model: Literal["deepseek-flash", "deepseek-v4-pro"] | None = None
    thinking: bool | None = None
    web_search: bool | None = None


class MessageRequest(BaseModel):
    request_id: str | None = Field(default=None, max_length=80)
    text: str = Field(min_length=1, max_length=12000)
    model: Literal["deepseek-flash", "deepseek-v4-pro"] | None = None
    thinking: bool = False
    web_search: bool = False
    attachment_ids: list[str] = Field(default_factory=list, max_length=6)
    image_ids: list[str] = Field(default_factory=list, max_length=6)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=24)
    password: str = Field(min_length=1, max_length=64, repr=False)
    remember: bool = False


class RegisterRequest(LoginRequest):
    name: str = Field(min_length=1, max_length=20)


class GuestEndRequest(BaseModel):
    client_id: str = Field(default="", max_length=80)


class ConsultationRequest(BaseModel):
    crop: Crop | None = None
    location: str = Field(default="", max_length=120)
    stage: str = Field(default="不清楚", max_length=40)
    variety: str = Field(default="", max_length=80)


class CaseUpdate(BaseModel):
    conversation_title: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
        | None
    ) = None
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
