# plugins/interactive_help/_handler.py
"""交互式帮助菜单的命令处理。

说明：
- `/help` 触发主菜单
- `/help <分类名>` 触发子菜单
- `/help_reload` 热重载配置（需管理员权限）

渲染方式由 `HELP_USE_CARD` 决定（默认纯文本）：
- 纯文本：个人号协议端（NapCat / Lagrange）唯一可靠的形式
- json 卡片：仅官方渠道机器人可正常渲染，发送失败会降级为文本
"""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.log import logger

from ._builder import (
    build_main_menu_json,
    build_main_menu_text,
    build_submenu_json,
    build_submenu_text,
    send_menu,
)
from ._config import config_manager, reload_config
from ._models import PermissionLevel
from ._permission import get_user_permission, has_permission


help_cmd = on_command(
    "help",
    aliases={"帮助", "菜单", "menu"},
    priority=10,
    block=True,
)

help_reload = on_command(
    "help_reload",
    aliases={"重载菜单"},
    priority=10,
    block=True,
)


async def _send_menu(
    bot: Bot,
    user_id: int,
    group_id: int | None,
    user_level: PermissionLevel,
    category_id: str | None = None,
) -> None:
    """按配置的渲染方式发送主菜单或子菜单。"""
    if config_manager.use_card:
        if category_id:
            await send_menu(
                bot, user_id=user_id, group_id=group_id,
                card_json=build_submenu_json(category_id, user_level),
            )
        else:
            await send_menu(
                bot, user_id=user_id, group_id=group_id,
                card_json=build_main_menu_json(user_level),
            )
        return

    text = (
        build_submenu_text(category_id, user_level)
        if category_id
        else build_main_menu_text(user_level)
    )
    await send_menu(bot, user_id=user_id, group_id=group_id, text=text)


@help_cmd.handle()
async def handle_help_command(bot: Bot, event: MessageEvent):
    """处理 /help 命令。

    支持：
    - /help       → 主菜单
    - /help 漫画  → 子菜单（按分类名匹配）
    """
    user_id = event.user_id
    group_id = event.group_id if hasattr(event, "group_id") else None
    user_level = get_user_permission(user_id, config_manager.permissions)

    # NoneBot 的 on_command 已经剥离命令前缀，get_message 剩余部分即参数
    arg_text = str(event.get_message()).strip()

    if arg_text:
        category_id = _match_category(arg_text, user_level)
        if category_id:
            await _send_menu(bot, user_id, group_id, user_level, category_id=category_id)
            return

    await _send_menu(bot, user_id, group_id, user_level)


@help_reload.handle()
async def handle_reload_command(bot: Bot, event: MessageEvent):
    """处理 /help_reload 命令，重新加载菜单配置。"""
    user_id = event.user_id
    group_id = event.group_id if hasattr(event, "group_id") else None
    user_level = get_user_permission(user_id, config_manager.permissions)

    # 仅管理员以上可重载
    if user_level < PermissionLevel.ADMIN:
        await bot.send_msg(
            message_type="private" if group_id is None else "group",
            user_id=user_id if group_id is None else None,
            group_id=group_id,
            message="你没有权限重载菜单配置。",
        )
        return

    reload_config()
    await bot.send_msg(
        message_type="private" if group_id is None else "group",
        user_id=user_id if group_id is None else None,
        group_id=group_id,
        message="菜单配置已重新加载。",
    )


def _match_category(arg: str, user_level: PermissionLevel) -> str | None:
    """根据用户输入匹配分类 ID。

    支持按分类 ID 或分类 label 匹配，返回匹配到的分类 ID。
    """
    menu = config_manager.menu
    categories = [
        cat
        for cat in menu.categories
        if has_permission(user_level, cat.permission)
    ]

    arg_lower = arg.lower()

    # 先按 ID 精确匹配
    for cat in categories:
        if cat.id.lower() == arg_lower:
            return cat.id

    # 再按 label 模糊匹配
    for cat in categories:
        if cat.label.lower() == arg_lower or arg_lower in cat.label.lower():
            return cat.id

    return None
