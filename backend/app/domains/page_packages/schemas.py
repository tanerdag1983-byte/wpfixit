from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


BuilderType = Literal["gutenberg", "elementor", "bricks", "wpbakery", "acf"]
SeoPluginType = Literal["yoast", "rank_math", "aioseo"]


class PagePackageSettingsWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    builder: BuilderType
    template_wordpress_page_id: str = Field(min_length=1, max_length=64)
    seo_plugin: SeoPluginType
    slot_mapping: dict[str, str] = Field(default_factory=dict)
