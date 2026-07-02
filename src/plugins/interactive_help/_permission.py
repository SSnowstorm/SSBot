# plugins/interactive_help/permission.py
"""权限等级定义与用户权限检查。"""

from nonebot import get_driver
from nonebot.log import logger

from ._models import PermissionLevel, PermissionsConfig


PERMISSION_MAP = {
    "banned": PermissionLevel.BANNED,
    "user": PermissionLevel.USER,
    "vip": PermissionLevel.VIP,
    "admin": PermissionLevel.ADMIN,
    "super_admin": PermissionLevel.SUPER_ADMIN,
}


STYLE_MAP = {
    "primary": 1,
    "success": 2,
    "warning": 3,
    "danger": 4,
    "default": 0,
}


def permission_from_str(value: str) -> PermissionLevel:
    """将字符串权限转换为 PermissionLevel。"""
    return PERMISSION_MAP.get(value.lower(), PermissionLevel.USER)


def style_value(style: str) -> int:
    """将样式名转换为 QQ 官方 keyboard 的 style 数值。"""
    return STYLE_MAP.get(style.lower(), 0)


def get_user_permission(user_id: int | str, permissions: PermissionsConfig) -> PermissionLevel:
    """获取用户权限等级。

    优先级：超级用户（NoneBot SUPERUSERS） > 封禁 > 管理员 > VIP > 普通用户
    """
    user_id = str(user_id)

    try:
        superusers = get_driver().config.superusers
    except Exception as e:
        logger.debug(f"读取 SUPERUSERS 失败: {e}")
        superusers = set()

    if user_id in superusers:
        return PermissionLevel.SUPER_ADMIN

    if user_id in permissions.banned_users:
        return PermissionLevel.BANNED

    if user_id in permissions.admins:
        return PermissionLevel.ADMIN

    if user_id in permissions.vip_users:
        return PermissionLevel.VIP

    return PermissionLevel.USER


def has_permission(user_level: PermissionLevel, required: str) -> bool:
    """检查用户权限是否满足要求。"""
    required_level = permission_from_str(required)
    return user_level >= required_level
