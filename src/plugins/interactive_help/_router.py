# plugins/interactive_help/router.py
"""按钮回调路由。

将按钮 callback_data 解析后分发到对应处理函数。
"""

from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.log import logger

from ._builder import build_submenu, send_menu
from ._config import config_manager
from ._models import MenuItem, PermissionLevel
from ._permission import get_user_permission, has_permission
from ._utils import decode_callback


async def handle_button_click(
    bot: Bot,
    event: Event,
    callback_data: str,
) -> None:
    """处理按钮点击回调。

    参数 callback_data 来自 QQ 按钮的回调数据；
    event 提供 user_id / group_id 等上下文。
    """
    payload = decode_callback(callback_data)
    if payload is None:
        logger.warning("无法解析按钮 callback_data")
        return

    action_type = payload.get("t")
    category_id = payload.get("cat", "main")
    item_id = payload.get("id")

    user_id = getattr(event, "user_id", None)
    group_id = getattr(event, "group_id", None)

    if user_id is None:
        logger.warning("按钮事件中缺少 user_id")
        return

    user_level = get_user_permission(user_id, config_manager.permissions)

    # 查找按钮对应配置
    item = _find_item(category_id, item_id)
    if item is None:
        logger.warning(f"未找到菜单项: cat={category_id}, id={item_id}")
        await _reply(bot, event, "该菜单项已失效或不存在。")
        return

    # 再次校验权限，防止用户伪造 callback_data
    if not has_permission(user_level, item.permission):
        await _reply(bot, event, "你没有权限使用该按钮。")
        return

    if action_type == "n":  # nav
        target = item.target or "main"
        if target == "main":
            from ._builder import build_main_menu
            text, keyboard = build_main_menu(user_level)
        else:
            text, keyboard = build_submenu(target, user_level)
        await send_menu(bot, user_id=user_id, group_id=group_id, text=text, keyboard=keyboard)

    elif action_type == "c":  # command
        await _reply(bot, event, f"请使用命令：/{item.action or item.id}")

    elif action_type == "a":  # action
        if item.action == "close_menu":
            await _reply(bot, event, "菜单已关闭。")
        else:
            await _reply(bot, event, f"动作 {item.action} 暂未实现。")

    else:
        logger.warning(f"未知按钮类型: {action_type}")


def _find_item(category_id: str, item_id: str) -> MenuItem | None:
    """根据分类 ID 和按钮 ID 查找菜单项。"""
    menu = config_manager.menu

    if category_id == "main":
        # 主菜单上的按钮是分类入口
        category = next((cat for cat in menu.categories if cat.id == item_id), None)
        if category is not None:
            return MenuItem(
                id=category.id,
                label=category.label,
                type="nav",
                target=category.id,
                style=category.style,
                permission=category.permission,
            )
        return None

    category = next((cat for cat in menu.categories if cat.id == category_id), None)
    if category is None:
        return None

    # 子菜单里可能还有返回按钮等内置项
    if item_id == "back":
        return MenuItem(
            id="back",
            label="← 返回主菜单",
            type="nav",
            target="main",
            style="default",
            permission="user",
        )

    return next((item for item in category.items if item.id == item_id), None)


async def _reply(bot: Bot, event: Event, text: str) -> None:
    """根据事件类型回复一条文本消息。"""
    group_id = getattr(event, "group_id", None)
    user_id = getattr(event, "user_id", None)

    if group_id is not None:
        await bot.send_group_msg(group_id=group_id, message=text)
    elif user_id is not None:
        await bot.send_private_msg(user_id=user_id, message=text)
