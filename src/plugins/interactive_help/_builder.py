# plugins/interactive_help/_builder.py
"""帮助菜单渲染器。

两种呈现方式：
- **纯文本**（默认）：第三方协议端（NapCat / Lagrange 等个人号）不渲染 `json` 卡片，
  文本是唯一可靠的形式。
- **json 卡片**：仅官方渠道机器人能正常渲染；通过环境变量 `HELP_USE_CARD=true` 开启。

修复记录（D-14，实机联调发现）：原实现只发 json 卡片，"降级为文本"仅在发送抛异常时触发；
个人号协议端往往"发送成功但客户端不渲染"，于是用户什么都看不到。现改为默认发文本，
需要卡片时显式开启，卡片发送失败仍会降级为文本。
"""

import json

from nonebot.adapters.onebot.v11 import Bot
from nonebot.log import logger

from ._config import config_manager
from ._models import MenuCategory, MenuItem, PermissionLevel
from ._permission import has_permission

# 单条文本消息的安全上限（QQ 单条消息过长会被截断或发送失败）
MAX_TEXT_LEN = 1500


def _filter_items(items: list[MenuItem], user_level: PermissionLevel) -> list[MenuItem]:
    """根据权限过滤菜单项。"""
    return [item for item in items if has_permission(user_level, item.permission)]


def _filter_categories(
    categories: list[MenuCategory], user_level: PermissionLevel
) -> list[MenuCategory]:
    """根据权限过滤分类。"""
    return [cat for cat in categories if has_permission(user_level, cat.permission)]


def _action_text(action: str) -> str:
    """命令展示文本：缺省补上命令前缀，避免出现『发送 sv』这种半截写法。"""
    text = str(action).strip()
    return text if text.startswith(("/", "／")) else "/" + text


def _clip(text: str, limit: int = MAX_TEXT_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n…（内容过长，已截断）"


# ============== 纯文本菜单 ==============

def build_main_menu_text(user_level: PermissionLevel = PermissionLevel.USER) -> str:
    """构建主菜单纯文本。"""
    menu = config_manager.menu
    categories = _filter_categories(menu.categories, user_level)

    lines = [f"📖 {menu.title}", menu.subtitle, ""]
    if not categories:
        lines.append("暂无可用菜单。")
    else:
        for cat in categories:
            items = _filter_items(cat.items, user_level)
            lines.append(f"【{cat.label}】")
            if items:
                for item in items:
                    lines.append(f"  {item.label}")
            else:
                lines.append("  （暂无命令）")
            lines.append("")

    lines.append("回复「/help <分类名>」查看分类详情，例如 /help 影之诗")
    return _clip("\n".join(lines).rstrip())


def build_submenu_text(
    category_id: str, user_level: PermissionLevel = PermissionLevel.USER
) -> str:
    """构建分类子菜单纯文本。"""
    menu = config_manager.menu
    category = next((cat for cat in menu.categories if cat.id == category_id), None)

    if category is None:
        return "分类不存在，请发送 /help 查看所有分类。"

    if not has_permission(user_level, category.permission):
        return "你没有权限查看该分类。"

    items = _filter_items(category.items, user_level)
    lines = [f"📖 {menu.title} - {category.label}", ""]
    if not items:
        lines.append("该分类下暂无可用命令。")
    else:
        for item in items:
            line = f"  {item.label}"
            if item.type == "command" and item.action:
                line += f"（发送 {_action_text(item.action)}）"
            lines.append(line)

    lines.append("")
    lines.append("回复「/help」返回主菜单")
    return _clip("\n".join(lines))


# ============== json 卡片（官方渠道机器人） ==============

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
                action_hint = f"（发送 {_action_text(item.action)}）"
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


# ============== 发送 ==============

async def _send_raw(bot: Bot, user_id: int | None, group_id: int | None, message) -> dict | None:
    if group_id is not None:
        return await bot.call_api("send_group_msg", group_id=group_id, message=message)
    if user_id is not None:
        return await bot.call_api("send_private_msg", user_id=user_id, message=message)
    raise ValueError("user_id 和 group_id 不能同时为空")


async def send_menu(
    bot: Bot,
    user_id: int | None = None,
    group_id: int | None = None,
    card_json: str = "",
    text: str = "",
) -> dict | None:
    """统一发送帮助菜单。

    - 传 text：直接发纯文本（默认路径，个人号协议端唯一可靠的形式）
    - 传 card_json：尝试发 json 卡片，失败或客户端不渲染时由调用方决定是否补发文本
    """
    if text:
        try:
            result = await _send_raw(bot, user_id, group_id, text)
            logger.debug(f"发送帮助文本成功: user={user_id}, group={group_id}")
            return result
        except Exception as e:
            logger.error(f"发送帮助文本失败: {e}")
            raise

    if not card_json:
        raise ValueError("text 与 card_json 至少要提供一个")

    message = [{"type": "json", "data": {"data": card_json}}]
    try:
        result = await _send_raw(bot, user_id, group_id, message)
        logger.debug(f"发送菜单卡片成功: user={user_id}, group={group_id}")
        return result
    except Exception as e:
        logger.error(f"发送菜单卡片失败: {e}")
        # 降级：从卡片 JSON 中提取描述文本作为降级消息
        try:
            card_dict = json.loads(card_json)
            news = card_dict.get("meta", {}).get("news", {})
            fallback_text = (
                f"{news.get('title', '')}\n{news.get('desc', '')}".strip()
            )
            result = await _send_raw(bot, user_id, group_id, fallback_text)
            logger.info("降级发送纯文本菜单成功")
            return result
        except Exception as fallback_err:
            logger.error(f"降级发送也失败: {fallback_err}")
            raise
