# plugins/interactive_help/models.py
"""交互式帮助菜单的数据模型。"""

from enum import IntEnum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class PermissionLevel(IntEnum):
    """权限等级，数值越大权限越高。"""

    BANNED = -1
    USER = 0
    VIP = 1
    ADMIN = 2
    SUPER_ADMIN = 3


class MenuItem(BaseModel):
    """菜单按钮配置。"""

    id: str = Field(..., description="菜单项唯一标识")
    label: str = Field(..., description="按钮显示文本")
    type: Literal["command", "nav", "action"] = Field("command", description="操作类型")
    action: Optional[str] = Field(None, description="命令名或动作名")
    target: Optional[str] = Field(None, description="导航目标（用于 nav 类型）")
    style: Literal["primary", "success", "warning", "danger", "default"] = Field(
        "default", description="按钮样式"
    )
    permission: Literal["banned", "user", "vip", "admin", "super_admin"] = Field(
        "user", description="所需最低权限"
    )

    @field_validator("type", mode="before")
    @classmethod
    def lowercase_type(cls, v: str) -> str:
        return str(v).lower()

    @field_validator("style", mode="before")
    @classmethod
    def lowercase_style(cls, v: str) -> str:
        return str(v).lower()

    @field_validator("permission", mode="before")
    @classmethod
    def lowercase_permission(cls, v: str) -> str:
        return str(v).lower()


class MenuCategory(BaseModel):
    """菜单分类配置。"""

    id: str = Field(..., description="分类唯一标识")
    label: str = Field(..., description="分类显示文本")
    style: Literal["primary", "success", "warning", "danger", "default"] = Field(
        "default", description="分类按钮样式"
    )
    permission: Literal["banned", "user", "vip", "admin", "super_admin"] = Field(
        "user", description="进入分类所需最低权限"
    )
    items: list[MenuItem] = Field(default_factory=list, description="分类下的菜单项")

    @field_validator("style", mode="before")
    @classmethod
    def lowercase_style(cls, v: str) -> str:
        return str(v).lower()

    @field_validator("permission", mode="before")
    @classmethod
    def lowercase_permission(cls, v: str) -> str:
        return str(v).lower()


class MenuConfig(BaseModel):
    """帮助菜单顶层配置。"""

    title: str = Field("SSBot 帮助菜单", description="菜单标题")
    subtitle: str = Field("点击下方分类查看功能", description="菜单副标题")
    categories: list[MenuCategory] = Field(default_factory=list, description="菜单分类")


class PermissionsConfig(BaseModel):
    """权限名单配置。"""

    admins: list[str] = Field(default_factory=list, description="管理员 QQ 列表")
    vip_users: list[str] = Field(default_factory=list, description="VIP 用户 QQ 列表")
    banned_users: list[str] = Field(default_factory=list, description="被封禁用户 QQ 列表")

    @field_validator("admins", "vip_users", "banned_users", mode="before")
    @classmethod
    def stringify_ids(cls, v: list | None) -> list[str]:
        if v is None:
            return []
        return [str(item) for item in v]


class HelpMenuRootConfig(BaseModel):
    """帮助菜单 YAML 根结构。"""

    menu: MenuConfig = Field(default_factory=MenuConfig)
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
