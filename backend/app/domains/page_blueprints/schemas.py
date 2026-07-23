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


class SnapshotTextField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=3, max_length=160)
    path: str = Field(min_length=1, max_length=512)
    label: str = Field(min_length=1, max_length=200)
    value_type: Literal[
        "plain_text",
        "rich_text",
        "heading",
        "button_text",
        "url",
        "seo_title",
        "meta_description",
        "focus_keyword",
    ]
    current_value: str
    required: bool = True
    max_length: int = Field(ge=1, le=20_000)


class SnapshotTextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=160)
    layout: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=200)
    semantic_role: Literal[
        "hero", "introduction", "benefits", "process", "faq", "cta", "content"
    ]
    fields: list[SnapshotTextField] = Field(min_length=1)


class SnapshotTextSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["snapshot-text-v1"]
    document_fields: list[SnapshotTextField] = Field(min_length=5)
    blocks: list[SnapshotTextBlock] = Field(min_length=1)

    def fields_by_id(self) -> dict[str, SnapshotTextField]:
        fields = self.document_fields + [
            field for block in self.blocks for field in block.fields
        ]
        if len({field.id for field in fields}) != len(fields):
            raise ValueError("snapshot field IDs must be unique")
        return {field.id: field for field in fields}
