# plugins/jm_downloader/models/comic_data.py
from pydantic import BaseModel, Field
from typing import List, Optional


class ComicInfo(BaseModel):
    """
    漫画信息的Pydantic模型，用于在业务逻辑层之间传递结构化数据。
    """
    id: str = Field(..., description="漫画ID")
    title: str = Field(..., description="漫画标题")
    author: Optional[str] = Field(None, description="作者")
    tags: List[str] = Field([], description="标签列表")
    cover_url: Optional[str] = Field(None, description="封面图片URL")
    description: Optional[str] = Field(None, description="漫画简介")
    pages: Optional[int] = Field(None, description="页数")

    class Config:
        # 允许通过属性名访问字典键，例如 comic_info.id 代替 comic_info["id"]
        # 在 Pydantic V2 中默认启用，V1 可能需要 explicitly setting
        # For Pydantic V1, this is `allow_population_by_field_name = True` or `arbitrary_types_allowed = True`
        # Using `extra = 'allow'` to be flexible with potential extra fields from API
        extra = "allow"
