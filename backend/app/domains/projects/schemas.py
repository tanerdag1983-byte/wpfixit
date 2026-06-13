from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ProjectCreate(BaseModel):
    organization_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    domain: HttpUrl

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    domain: str
    timezone: str
    created_at: datetime


class ProjectList(BaseModel):
    items: list[ProjectRead]

