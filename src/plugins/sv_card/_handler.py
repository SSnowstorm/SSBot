# plugins/sv_card/_handler.py
"""影之诗超凡世界 查卡器命令处理。

支持命令：
    /sv <关键词>       模糊搜索卡片
    /sv #<职业>        按职业过滤
    /sv !<ID>          按卡牌ID精确查询
    /sv_reload         重新加载卡牌数据
"""

import re
from typing import Optional

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.log import logger

from ._cache import card_cache, reload_cards
from ._formatter import format_card_list, format_single_card, format_search_results
from ._searcher import search_cards


# ============== 命令定义 ==============

sv_cmd = on_command(
    "sv",
    aliases={"影之诗", "SV", "查卡"},
    priority=10,
    block=True,
)

sv_reload = on_command(
    "sv_reload",
    aliases={"重载卡库", "sv_reload"},
    priority=10,
    block=True,
)


# ============== 参数提取 ==============

# 匹配命令前缀：/sv  或  sv （后接可选空白 + 参数）
_CMD_PREFIX_RE = re.compile(
    r"^\s*(?:[/／\\]?(?:sv|SV|影之诗|查卡))\s*(.*)$",
    flags=re.IGNORECASE,
)


def _extract_keyword(event: MessageEvent) -> str:
    """从消息事件中提取命令参数（自动剥离命令前缀）。

    NoneBot2 的 on_command 已通过 rule 匹配了命令，但
    `event.get_message()` 拿到的仍可能是整条原始消息（含 /sv 等）。
    这里用纯文本 + 正则剥离掉命令前缀。
    """
    raw = event.get_plaintext().strip()
    m = _CMD_PREFIX_RE.match(raw)
    if m:
        return m.group(1).strip()
    # 兜底：没匹配上时返回原文（便于排错）
    return raw


# ============== 命令处理 ==============

@sv_cmd.handle()
async def handle_sv_command(bot: Bot, event: MessageEvent):
    """处理 /sv 命令，支持模糊搜索和精确查询。"""
    # 提取命令参数（自动剥离 /sv 前缀）
    arg_text = _extract_keyword(event)

    if not arg_text:
        await _send_help(bot, event)
        return

    # 检查是否为ID精确查询 (!ID)
    id_match = re.match(r'^!(\d+)$', arg_text)
    if id_match:
        card_id = id_match.group(1)
        await _handle_id_query(bot, event, card_id)
        return

    # 检查是否为职业过滤 (#职业)
    class_match = re.match(r'^#(\S+)$', arg_text)
    if class_match:
        class_filter = class_match.group(1)
        await _handle_class_filter(bot, event, class_filter)
        return

    # 模糊搜索
    await _handle_search(bot, event, arg_text)


@sv_reload.handle()
async def handle_reload_command(bot: Bot, event: MessageEvent):
    """重新加载卡牌数据。"""
    try:
        await reload_cards()
        await bot.send(
            event=event,
            message="✅ 卡牌数据已重新加载。",
        )
    except Exception as e:
        logger.error(f"重载卡牌数据失败: {e}")
        await bot.send(
            event=event,
            message=f"❌ 重载失败: {str(e)}",
        )


# ============== 内部处理方法 ==============

async def _send_help(bot: Bot, event: MessageEvent):
    """发送帮助信息。"""
    help_text = """📖 影之诗：超凡世界 查卡器

【命令格式】
/sv <关键词>       模糊搜索卡片
/sv #<职业>        按职业过滤
/sv !<ID>          按卡牌ID精确查询
/sv_reload         重新加载数据

【职业代码】
#剑  #森林  #龙  #死  #主教  #魂
#中立

【示例】
/sv Albert
/sv #剑
/sv !10124110
"""
    await bot.send(event=event, message=help_text)


async def _handle_id_query(bot: Bot, event: MessageEvent, card_id: str):
    """处理ID精确查询。"""
    card = card_cache.get_card_by_id(card_id)

    if not card:
        await bot.send(
            event=event,
            message=f"❌ 未找到ID为 {card_id} 的卡牌。",
        )
        return

    msg = format_single_card(card)
    await bot.send(event=event, message=msg)
    # TODO: 发送卡片图片


async def _handle_class_filter(bot: Bot, event: MessageEvent, class_filter: str):
    """处理职业过滤查询。"""
    cards = card_cache.get_all_cards()
    filtered = search_cards(class_filter, cards, class_filter_only=True)

    if not filtered:
        await bot.send(
            event=event,
            message=f"❌ 未找到职业「{class_filter}」的卡牌。",
        )
        return

    # 限制返回数量
    results = filtered[:10]
    msg = format_search_results(results, class_filter)

    await bot.send(event=event, message=msg)
    # TODO: 发送卡片图片列表


async def _handle_search(bot: Bot, event: MessageEvent, keyword: str):
    """处理模糊搜索。"""
    cards = card_cache.get_all_cards()
    results = search_cards(keyword, cards)

    if not results:
        await bot.send(
            event=event,
            message=f"❌ 未找到包含「{keyword}」的卡牌。",
        )
        return

    # 根据结果数量决定展示方式
    if len(results) == 1:
        # 精确匹配单个结果
        msg = format_single_card(results[0])
    else:
        # 多个结果，展示列表
        msg = format_search_results(results, keyword)

    await bot.send(event=event, message=msg)
    # TODO: 发送卡片图片
