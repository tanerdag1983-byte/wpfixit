from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BlueprintField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    path: str
    label: str
    value_type: Literal["plain_text", "rich_text", "heading", "button_text", "url"]
    current_value: str
    required: bool = True
    max_length: int = Field(ge=1, le=20_000)


class BlueprintBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    layout: str
    label: str
    semantic_role: Literal[
        "hero", "introduction", "benefits", "process", "faq", "cta", "content"
    ]
    fields: list[BlueprintField] = Field(min_length=1)


class BlueprintSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["blueprint-v1"]
    blocks: list[BlueprintBlock] = Field(min_length=1)
