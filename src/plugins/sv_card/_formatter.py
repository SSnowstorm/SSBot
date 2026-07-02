# plugins/sv_card/_formatter.py
"""影之诗超凡世界 卡牌信息格式化。

功能：
    - 格式化单卡详情为文本消息
    - 格式化搜索结果列表
    - 清理技能描述中的HTML标签
"""

import re
from typing import Optional

from ._cache import CLASS_CODE_TO_NAME, RARITY_CODE_TO_NAME


def format_single_card(card: dict) -> str:
    """格式化单张卡牌为文本消息。

    Args:
        card: 卡牌数据

    Returns:
        格式化的文本消息
    """
    # 基础信息
    card_id = card.get("id", "")
    name = card.get("name", "未知")
    card_type = _translate_type(card.get("type", ""))
    cost = card.get("cost", "-")
    atk = card.get("atk", "-")
    life = card.get("life", "-")

    # 职业与稀有度
    class_code = str(card.get("class", "0"))
    class_name = _translate_class(card.get("color", ""), class_code)
    rarity_code = str(card.get("rarity", "1"))
    rarity_name = RARITY_CODE_TO_NAME.get(rarity_code, "铜")

    # 技能描述
    skill_text = _clean_html(card.get("skill_text", ""))
    evo_skill_text = _clean_html(card.get("evo_skill_text", ""))

    # 风味文本
    flavour_text = _clean_html(card.get("flavour_text", ""))

    # 插画师与CV
    illustrator = card.get("illustrator", "")
    cv = card.get("cv", "")

    # 构建消息
    lines = []

    # 标题行
    lines.append(f"━━━━ {name} ━━━━")
    lines.append(f"【{rarity_name}】【{class_name}】【{card_type}】")
    lines.append(f"费用: {cost}  攻击: {atk}  生命: {life}")

    # 分隔线
    lines.append("─" * 20)

    # 技能描述
    if skill_text:
        lines.append(f"【技能】{skill_text}")

    # 进化技能
    if evo_skill_text:
        lines.append(f"【进化】{evo_skill_text}")

    # 风味文本
    if flavour_text:
        lines.append(f"「{flavour_text}」")

    # 分隔线
    lines.append("─" * 20)

    # 附加信息
    info_parts = []
    if illustrator:
        info_parts.append(f"画师: {illustrator}")
    if cv:
        info_parts.append(f"CV: {cv}")

    if info_parts:
        lines.append(" | ".join(info_parts))

    # 卡片ID
    lines.append(f"[ID: {card_id}]")

    return "\n".join(lines)


def format_search_results(cards: list[dict], keyword: str) -> str:
    """格式化搜索结果列表。

    Args:
        cards: 卡牌列表
        keyword: 搜索关键词

    Returns:
        格式化的文本消息
    """
    if not cards:
        return f"未找到包含「{keyword}」的卡牌。"

    lines = []
    lines.append(f"🔍 搜索「{keyword}」找到 {len(cards)} 张卡牌：")
    lines.append("")

    for i, card in enumerate(cards, 1):
        # 基础信息
        name = card.get("name", "未知")
        card_type = _translate_type(card.get("type", ""))
        cost = card.get("cost", "-")
        atk = card.get("atk", "-")
        life = card.get("life", "-")

        # 职业与稀有度
        class_code = str(card.get("class", "0"))
        class_name = _translate_class(card.get("color", ""), class_code)
        rarity_code = str(card.get("rarity", "1"))
        rarity_name = RARITY_CODE_TO_NAME.get(rarity_code, "铜")

        # 简化的技能描述（只取第一行）
        skill_text = _clean_html(card.get("skill_text", ""))
        if len(skill_text) > 30:
            skill_text = skill_text[:27] + "..."

        # 格式化行
        status = f"{cost}费" if cost != "-" else ""
        status += f"/{atk}攻" if atk != "-" else ""
        status += f"/{life}血" if life != "-" else ""

        line = f"{i}. {name}"
        line += f" [{rarity_name}][{class_name}][{card_type}]"
        if status:
            line += f" {status}"

        if skill_text:
            line += f"\n   {skill_text}"

        lines.append(line)

    if len(cards) == 10:
        lines.append("")
        lines.append(f"（仅显示前10条结果，请使用更精确的关键词）")

    return "\n".join(lines)


def format_card_list(cards: list[dict], title: str = "") -> str:
    """格式化卡牌列表（简洁模式）。

    Args:
        cards: 卡牌列表
        title: 列表标题

    Returns:
        格式化的文本消息
    """
    if not cards:
        return "卡牌列表为空。"

    lines = []
    if title:
        lines.append(f"━━━ {title} ━━━")
        lines.append("")

    for i, card in enumerate(cards, 1):
        name = card.get("name", "未知")
        card_id = card.get("id", "")
        lines.append(f"{i}. {name} [{card_id}]")

    return "\n".join(lines)


def _translate_type(card_type: str) -> str:
    """翻译卡牌类型为中文。"""
    type_map = {
        "follower": "随从",
        "spell": "法术",
        "amulet": "护符",
        "token": "衍生物",
        "token follower": "衍生物",
        "enhance": "强化",
    }
    return type_map.get(card_type.lower(), card_type)


def _translate_class(color: str, class_code: str) -> str:
    """翻译职业为中文。"""
    # 优先使用职业代码
    chinese_name = CLASS_CODE_TO_NAME.get(class_code)
    if chinese_name:
        return chinese_name

    # 使用英文颜色名称
    color_lower = color.lower()
    if "forest" in color_lower:
        return "森林"
    elif "sword" in color_lower:
        return "剑"
    elif "rune" in color_lower:
        return "龙"
    elif "dragon" in color_lower:
        return "龙"
    elif "abyss" in color_lower:
        return "死"
    elif "haven" in color_lower:
        return "主教"
    elif "portal" in color_lower:
        return "魂"
    elif "neutral" in color_lower:
        return "中立"

    return color or "中立"


def _clean_html(text: str) -> str:
    """清理HTML标签，保留文本内容。

    Args:
        text: 包含HTML的原始文本

    Returns:
        清理后的纯文本
    """
    if not text:
        return ""

    # 替换换行标签
    text = text.replace("<br>", "\n")
    text = text.replace("<br/>", "\n")
    text = text.replace("<br />", "\n")
    text = text.replace("\\n", "\n")

    # 移除所有HTML标签
    text = re.sub(r"<[^>]+>", "", text)

    # 清理多余的空白
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    return text


def _format_skill_text(skill_text: str, max_length: int = 100) -> str:
    """格式化技能描述，限制长度。

    Args:
        skill_text: 原始技能描述
        max_length: 最大长度

    Returns:
        格式化后的技能描述
    """
    text = _clean_html(skill_text)

    if len(text) <= max_length:
        return text

    return text[: max_length - 3] + "..."


def get_card_image_url(card: dict, lang: str = "en") -> Optional[str]:
    """获取卡牌图片URL。

    Args:
        card: 卡牌数据
        lang: 语言代码（en, chs, cht, ja, ko）

    Returns:
        卡牌图片URL
    """
    # 优先使用卡片自带的图片URL
    image_url = card.get("image")
    if image_url:
        return image_url

    # 尝试从ID构造图片URL
    card_id = card.get("id")
    if card_id:
        # shadowverse-portal的图片URL格式
        return f"https://shadowverse-portal.com/image/card/{lang}/C_{card_id}.png"

    return None
