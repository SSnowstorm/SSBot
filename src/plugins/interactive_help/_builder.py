# plugins/interactive_help/builder.py
"""帮助菜单卡片构建器。

负责把 YAML 配置转换成 QQ 结构化卡片（json 消息段）。
当前使用 com.tencent.structmsg 的 news 视图生成卡片外观，
依赖 NapCat / Lagrange 等协议端对 json 消息段的支持。

注意：json 卡片只有外观展示能力，没有按钮交互能力。
后续若切换到 QQ 官方适配器，可改用 ark + keyboard 实现完整交互。
"""

import json
import time

from nonebot.adapters.onebot.v11 import Bot
from nonebot.log import logger

from ._config import config_manager
from ._models import MenuCategory, MenuConfig, MenuItem, PermissionLevel
from ._permission import has_permission


def _filter_items(items: list[MenuItem], user_level: PermissionLevel) -> list[MenuItem]:
    """根据权限过滤菜单项。"""
    return [item for item in items if has_permission(user_level, item.permission)]


def _filter_categories(
    categories: list[MenuCategory], user_level: PermissionLevel
) -> list[MenuCategory]:
    """根据权限过滤分类。"""
    return [cat for cat in categories if has_permission(user_level, cat.permission)]


def build_main_menu_json(user_level: PermissionLevel = PermissionLevel.USER) -> str:
    """构建主菜单的 JSON 卡片数据字符串。

    返回可直接作为 json 消息段 data 字段的 JSON 字符串。
    """
    menu = config_manager.menu
    categories = _filter_categories(menu.categories, user_level)

    # 构建分类描述文本
    if not categories:
        desc_text = "暂无可用菜单。"
    else:
        lines = []
        for cat in categories:
            items = _filter_items(cat.items, user_level)
            item_names = " | ".join(item.label for item in items) if items else "暂无命令"
            lines.append(f"▸ {cat.label}：{item_names}")
        desc_text = "\n".join(lines)
        desc_text += "\n\n回复分类名查看详细命令"

    card_data = {
        "app": "com.tencent.structmsg",
        "desc": "",
        "view": "news",
        "ver": "0.0.0.1",
        "prompt": f"[帮助菜单]{menu.title}",
        "meta": {
            "news": {
                "action": "",
                "android_pkg_name": "",
                "app_type": 1,
                "appid": 0,
                "desc": desc_text,
                "jumpUrl": "",
                "preview": "",
                "source_icon": "",
                "source_url": "",
                "tag": "帮助",
                "title": menu.title,
            }
        },
        "text": "",
        "extraApps": [],
        "sourceAd": "",
    }

    return json.dumps(card_data, ensure_ascii=False, separators=(",", ":"))


def build_submenu_json(
    category_id: str, user_level: PermissionLevel = PermissionLevel.USER
) -> str:
    """构建子菜单的 JSON 卡片数据字符串。"""
    menu = config_manager.menu
    category = next((cat for cat in menu.categories if cat.id == category_id), None)

    if category is None:
        # 分类不存在时发简单纯文本提示
        return _build_text_card("分类不存在", "请通过 /help 查看所有分类")

    if not has_permission(user_level, category.permission):
        return _build_text_card("权限不足", "你没有权限查看该分类")

    items = _filter_items(category.items, user_level)

    if not items:
        desc_text = "该分类下暂无可用命令。"
    else:
        lines = []
        for item in items:
            action_hint = ""
            if item.type == "command" and item.action:
                action_hint = f"（发送 {item.action}）"
            lines.append(f"▸ {item.label}{action_hint}")
        desc_text = "\n".join(lines)
        desc_text += "\n\n回复 /help 返回主菜单"

    card_data = {
        "app": "com.tencent.structmsg",
        "desc": "",
        "view": "news",
        "ver": "0.0.0.1",
        "prompt": f"[帮助菜单]{category.label}",
        "meta": {
            "news": {
                "action": "",
                "android_pkg_name": "",
                "app_type": 1,
                "appid": 0,
                "desc": desc_text,
                "jumpUrl": "",
                "preview": "",
                "source_icon": "",
                "source_url": "",
                "tag": category.label,
                "title": f"{menu.title} - {category.label}",
            }
        },
        "text": "",
        "extraApps": [],
        "sourceAd": "",
    }

    return json.dumps(card_data, ensure_ascii=False, separators=(",", ":"))


def _build_text_card(title: str, desc: str) -> str:
    """构建简单的纯文本卡片（用于提示消息）。"""
    card_data = {
        "app": "com.tencent.structmsg",
        "desc": "",
        "view": "news",
        "ver": "0.0.0.1",
        "prompt": f"[帮助菜单]{title}",
        "meta": {
            "news": {
                "action": "",
                "android_pkg_name": "",
                "app_type": 1,
                "appid": 0,
                "desc": desc,
                "jumpUrl": "",
                "preview": "",
                "source_icon": "",
                "source_url": "",
                "tag": "帮助",
                "title": title,
            }
        },
        "text": "",
        "extraApps": [],
        "sourceAd": "",
    }
    return json.dumps(card_data, ensure_ascii=False, separators=(",", ":"))


async def send_menu(
    bot: Bot,
    user_id: int | None = None,
    group_id: int | None = None,
    card_json: str = "",
) -> dict | None:
    """统一发送菜单卡片消息。

    私聊用 user_id，群聊用 group_id。
    通过 bot.call_api 发送包含 json 消息段的消息。
    """
    # 构造消息数组：json 消息段
    message = [{"type": "json", "data": {"data": card_json}}]

    try:
        if group_id is not None:
            result = await bot.call_api(
                "send_group_msg", group_id=group_id, message=message
            )
        elif user_id is not None:
            result = await bot.call_api(
                "send_private_msg", user_id=user_id, message=message
            )
        else:
            raise ValueError("user_id 和 group_id 不能同时为空")

        logger.debug(f"发送菜单卡片成功: user={user_id}, group={group_id}")
        return result
    except Exception as e:
        logger.error(f"发送菜单卡片失败: {e}")
        # 降级：发送纯文本
        try:
            # 从卡片 JSON 中提取描述文本作为降级消息
            card_dict = json.loads(card_json)
            desc = card_dict.get("meta", {}).get("news", {}).get("desc", "")
            title = card_dict.get("meta", {}).get("news", {}).get("title", "")
            fallback_text = f"{title}\n{desc}" if title else desc

            if group_id is not None:
                result = await bot.call_api(
                    "send_group_msg", group_id=group_id, message=fallback_text
                )
            elif user_id is not None:
                result = await bot.call_api(
                    "send_private_msg", user_id=user_id, message=fallback_text
                )
            else:
                raise
            logger.info(f"降级发送纯文本菜单成功")
            return result
        except Exception as fallback_err:
            logger.error(f"降级发送也失败: {fallback_err}")
            raise
