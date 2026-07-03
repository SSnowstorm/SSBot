# plugins/sv_card/_formatter.py
"""影之诗超凡世界 卡牌信息格式化。

功能：
    - 格式化单卡详情为文本消息
    - 格式化搜索结果列表
    - 处理 skill_text 中的格式标签（<color> <ev> <sev> <hr> <ridx>）
    - 翻译质量提示：skill_text 残留假名时附日文原文对照

注意：
    - 不显示 flavour_text（用户决定：风味文本翻译质量差，不展示）
    - type/rarity 已从 int 转换为中文名
    - class 从 card_id[3] 推断，已转 class_code + class_name
"""

import re
from typing import Optional


# ============== 格式标签处理 ==============

# skill_text 中的标签语义对照（用于简化显示）
# 注意：原始数据里 <color=Keyword> 是大写 K，但部分可能是 <color=keyword>
# 为安全起见使用正则处理
_IMPORT_RE = re.compile(r'<color=([^>]+)>', re.IGNORECASE)
_CLOSE_RE = re.compile(r'</color>', re.IGNORECASE)


def _render_skill_text(text: str) -> str:
    """把 skill_text 中的格式标签转换为更适合纯文本显示的形式。

    原始数据的特点（用户翻译时加的）：
        - 已经用中文方括号【...】标记每个效果段
        - 用 <color=Keyword>...</color> 高亮关键词
        - 用 <ev>...</ev> 标记进化效果
        - 用 <sev>...</sev> 标记超进化效果
        - 用 <hr> 标记基础/进化分隔
        - 用 <ridx=N>...</ridx> 标记选项块

    渲染策略：去掉 HTML 风格的 <...> 标签，保留中文方括号，仅对特殊标签加修饰：
        <color=...>...</color>  → 直接去掉（保留内部文字，外层【】已存在）
        <ev>...</ev>           → 前面加 ↳ 进化时：
        <sev>...</sev>         → 前面加 ↳ 超进化时：
        <hr>                   → 单独一行 ────
        <ridx=N>...</ridx>     → （N+1）...
    """
    if not text:
        return ""

    out = text

    # 1) 超进化 / 进化（不区分大小写）
    out = re.sub(r'<sev>', '\n↳ 超进化时：', out, flags=re.IGNORECASE)
    out = re.sub(r'</sev>', '', out, flags=re.IGNORECASE)
    out = re.sub(r'<ev>', '\n↳ 进化时：', out, flags=re.IGNORECASE)
    out = re.sub(r'</ev>', '', out, flags=re.IGNORECASE)

    # 2) 分隔线
    out = re.sub(r'<hr>', '\n────────\n', out, flags=re.IGNORECASE)

    # 3) 选项块：保留标签内的（1）（2）原文，只去掉 <ridx=N> </ridx> 标签
    out = re.sub(r'<ridx=\d+>', '', out, flags=re.IGNORECASE)
    out = re.sub(r'</ridx>', '', out, flags=re.IGNORECASE)

    # 4) 颜色标签：去掉 <color=...> 和 </color>，只留下内部文字
    out = re.sub(r'<color=[^>]+>', '', out, flags=re.IGNORECASE)
    out = re.sub(r'</color>', '', out, flags=re.IGNORECASE)

    # 5) 任何残留的 <...> 标签全部移除
    out = re.sub(r'<[^>]+>', '', out)

    # 6) 多余空白清理
    out = re.sub(r'\n{3,}', '\n\n', out)
    out = re.sub(r' {2,}', ' ', out)
    return out.strip()


# ============== 单卡详情 ==============

def format_single_card(card: dict) -> str:
    """格式化单张卡牌为文本消息。"""
    # 基础信息
    card_id = card.get("id", "")
    name = card.get("name") or "未知"
    name_ja = card.get("name_ja", "")

    class_name = card.get("class_name", "中立")
    type_name = card.get("type_name", "未知")
    rarity_name = card.get("rarity_name", "铜")
    cost = card.get("cost", 0)
    atk = card.get("atk", 0)
    life = card.get("life", 0)

    # 技能描述（含翻译质量提示）
    skill_text = _render_skill_text(card.get("skill_text", ""))
    skill_text_ja = _render_skill_text(card.get("skill_text_ja", ""))
    skill_has_kana = card.get("skill_has_kana", False)

    # 进化技能（API 恒空，进化效果已在 skill_text 的 <ev> 中处理）
    evo_skill_text = _render_skill_text(card.get("evo_skill_text", ""))

    # 插画师 & CV
    illustrator = card.get("illustrator", "")
    cv = card.get("cv", "")

    # 种族
    tribes = card.get("tribes", []) or []

    lines = []

    # 标题（中日文对照）
    if name_ja and name_ja != name:
        lines.append(f"━━━━ {name} ━━━━")
        lines.append(f"  日文: {name_ja}")
    else:
        lines.append(f"━━━━ {name} ━━━━")

    # 属性行
    lines.append(f"【{rarity_name}】【{class_name}】【{type_name}】")
    lines.append(f"费用: {cost}  攻击: {atk}  生命: {life}")

    # 种族
    if tribes:
        tribe_names = [_tribe_to_name(t) for t in tribes if t]
        if tribe_names:
            lines.append(f"种族: {' / '.join(tribe_names)}")

    lines.append("─" * 20)

    # 技能描述
    if skill_text:
        lines.append(f"【技能】{skill_text}")

    # 进化技能（备用，正常情况已通过 <ev> 显示）
    if evo_skill_text:
        lines.append(f"【进化】{evo_skill_text}")

    # 翻译质量提示
    if skill_has_kana and skill_text_ja and skill_text_ja != skill_text:
        lines.append("")
        lines.append(f"【日文】{skill_text_ja}")

    # 分隔
    lines.append("─" * 20)

    # 附加信息
    info_parts = []
    if illustrator:
        info_parts.append(f"画师: {illustrator}")
    if cv:
        info_parts.append(f"CV: {cv}")
    if info_parts:
        lines.append(" | ".join(info_parts))

    # 卡片 ID
    lines.append(f"[ID: {card_id}]")

    return "\n".join(lines)


# ============== 搜索结果列表 ==============

def format_search_results(cards: list[dict], keyword: str) -> str:
    """格式化搜索结果列表。"""
    if not cards:
        return f"未找到包含「{keyword}」的卡牌。"

    lines = []
    lines.append(f"🔍 搜索「{keyword}」找到 {len(cards)} 张卡牌：")
    lines.append("")

    for i, card in enumerate(cards, 1):
        name = card.get("name") or "未知"
        class_name = card.get("class_name", "中立")
        type_name = card.get("type_name", "未知")
        rarity_name = card.get("rarity_name", "铜")
        cost = card.get("cost", 0)
        atk = card.get("atk", 0)
        life = card.get("life", 0)

        # 简化的技能描述（只取第一行）
        skill_text = _render_skill_text(card.get("skill_text", ""))
        first_line = skill_text.split("\n", 1)[0] if skill_text else ""
        if len(first_line) > 30:
            first_line = first_line[:27] + "..."

        # 状态行
        status_parts = []
        if cost:
            status_parts.append(f"{cost}费")
        if atk:
            status_parts.append(f"{atk}攻")
        if life:
            status_parts.append(f"{life}血")
        status = "/".join(status_parts)

        line = f"{i}. {name}"
        line += f" [{rarity_name}][{class_name}][{type_name}]"
        if status:
            line += f" {status}"

        if first_line:
            line += f"\n   {first_line}"

        # 翻译质量提示（仅在严重残留时提示）
        if card.get("skill_has_kana"):
            line += "  ※含日文残留"

        lines.append(line)

    if len(cards) >= 10:
        lines.append("")
        lines.append("（仅显示前10条结果，请使用更精确的关键词）")

    return "\n".join(lines)


def format_card_list(cards: list[dict], title: str = "") -> str:
    """格式化卡牌列表（简洁模式）。"""
    if not cards:
        return "卡牌列表为空。"

    lines = []
    if title:
        lines.append(f"━━━ {title} ━━━")
        lines.append("")

    for i, card in enumerate(cards, 1):
        name = card.get("name") or "未知"
        card_id = card.get("id", "")
        class_name = card.get("class_name", "")
        lines.append(f"{i}. {name} [{class_name}] [{card_id}]")

    return "\n".join(lines)


# ============== 辅助函数 ==============

# 种族代码 → 中文名（与 tribes 字段对应）
_TRIBE_CODE_TO_NAME = {
    0: "",
    1: "人类",
    2: "精灵",
    3: "野兽",
    4: "魔法师",
    5: "龙",
    6: "恶魔",
    7: "不死",
    8: "神",
    9: "武人",
    10: "机械",
    11: "造物",
}


def _tribe_to_name(tribe_code: int) -> str:
    """种族代码 → 中文名。"""
    return _TRIBE_CODE_TO_NAME.get(tribe_code, "")


# ============== 图片 URL ==============

def get_card_image_url(card: dict, lang: str = "cht") -> Optional[str]:
    """获取卡牌图片 URL。

    Args:
        card: 卡牌数据
        lang: 语言代码（en/chs/cht/ja/ko），默认 cht（繁体，bot 图片可显示）

    Returns:
        卡牌图片 URL
    """
    # 用户数据里 base_card_image_id 恒空，直接用 card_id 拼
    card_id = card.get("id")
    if card_id:
        return f"https://shadowverse-portal.com/image/card/{lang}/C_{card_id}.png"
    return None
