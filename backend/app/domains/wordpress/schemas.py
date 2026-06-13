from pydantic import BaseModel, Field, HttpUrl


class WordPressConnectRequest(BaseModel):
    site_url: HttpUrl
    secret: str = Field(min_length=32, max_length=256)


class WordPressConnectionRead(BaseModel):
    project_id: str
    site_url: str
    plugin_version: str | None
    seo_plugin: str | None
    health_state: str

