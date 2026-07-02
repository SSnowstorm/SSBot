# plugins/sv_card/_searcher.py
"""影之诗超凡世界 模糊搜索算法。

搜索优先级：
    1. 完整匹配（名称完全相等）→ score = 100
    2. 前缀匹配（名称以关键词开头）→ score = 80
    3. 包含匹配（名称包含关键词）→ score = 60
    4. 技能描述匹配 → score = 30
    5. 种族/类型匹配 → score = 20

支持多关键词搜索（空格分隔）
支持职业过滤（class_filter_only=True）
"""

from typing import Optional

from ._cache import CLASS_NAME_TO_CODE


def search_cards(
    keyword: str,
    cards: list[dict],
    class_filter_only: bool = False,
    limit: int = 10,
) -> list[dict]:
    """模糊搜索卡牌。

    Args:
        keyword: 搜索关键词
        cards: 卡牌列表
        class_filter_only: 是否仅按职业过滤
        limit: 最大返回数量

    Returns:
        按相关性排序的卡牌列表
    """
    if not keyword or not cards:
        return []

    # 解析关键词（支持多关键词空格分隔）
    keywords = keyword.lower().split()
    if not keywords:
        return []

    results: list[tuple[dict, int]] = []

    for card in cards:
        score = _calculate_score(card, keywords, class_filter_only)
        if score > 0:
            results.append((card, score))

    # 按分数降序排序
    results.sort(key=lambda x: -x[1])

    # 返回去重后的结果
    seen_ids = set()
    unique_results = []
    for card, score in results:
        card_id = card.get("id", "")
        if card_id not in seen_ids:
            seen_ids.add(card_id)
            unique_results.append(card)
            if len(unique_results) >= limit:
                break

    return unique_results


def _calculate_score(
    card: dict,
    keywords: list[str],
    class_filter_only: bool,
) -> int:
    """计算单张卡牌与关键词的匹配分数。

    Args:
        card: 卡牌数据
        keywords: 关键词列表
        class_filter_only: 是否仅按职业过滤

    Returns:
        匹配分数（0表示不匹配）
    """
    if class_filter_only:
        return _calculate_class_score(card, keywords)

    total_score = 0
    name = card.get("name", "").lower()
    skill_text = card.get("skill_text", "").lower()
    flavour_text = card.get("flavour_text", "").lower()
    card_type = card.get("type", "").lower()

    for keyword in keywords:
        keyword_score = 0

        # 1. 完整匹配（名称完全相等）
        if name == keyword:
            keyword_score = 100
        # 2. 前缀匹配
        elif name.startswith(keyword):
            keyword_score = 80
        # 3. 包含匹配
        elif keyword in name:
            keyword_score = 60
        # 4. 技能描述匹配
        elif keyword in skill_text:
            keyword_score = 30
        # 5. 风味文本匹配
        elif keyword in flavour_text:
            keyword_score = 15
        # 6. 类型匹配（随从、法术等）
        elif keyword in card_type:
            keyword_score = 10

        if keyword_score == 0:
            # 有任何关键词完全不匹配，该卡牌不符合条件
            return 0

        total_score += keyword_score

    return total_score


def _calculate_class_score(card: dict, keywords: list[str]) -> int:
    """计算职业过滤的匹配分数。

    Args:
        card: 卡牌数据
        keywords: 关键词列表（职业名）

    Returns:
        匹配分数（>0表示匹配）
    """
    card_class = str(card.get("class", ""))
    color = card.get("color", "").lower()

    for keyword in keywords:
        # 检查职业代码
        if keyword in CLASS_NAME_TO_CODE:
            target_code = CLASS_NAME_TO_CODE[keyword]
            if card_class == target_code:
                return 100

        # 检查职业名称（英文）
        if keyword.lower() in color:
            return 100

        # 检查职业名称（中文）
        if _match_chinese_class(card_class, keyword):
            return 100

    return 0


def _match_chinese_class(class_code: str, keyword: str) -> bool:
    """匹配中文职业名称。"""
    chinese_names = {
        "0": ["中立", "neutral"],
        "1": ["森林", "forest", "精灵"],
        "2": ["剑", "剑士", "sword", "皇家"],
        "3": ["龙", "龙族", "rune", "巫师"],
        "4": ["龙", "龙族", "dragon"],
        "5": ["死", "死灵", "abyss", "吸血鬼"],
        "6": ["主教", "haven", "教会"],
        "7": ["魂", "portal", "魂", "复仇"],
    }

    keywords = chinese_names.get(class_code, [])
    return keyword.lower() in [k.lower() for k in keywords]


def fuzzy_match_score(keyword: str, text: str) -> int:
    """计算两个字符串的模糊匹配分数。

    使用编辑距离和前缀匹配综合评分。

    Args:
        keyword: 关键词
        text: 待匹配文本

    Returns:
        匹配分数（0-100）
    """
    if not keyword or not text:
        return 0

    keyword = keyword.lower()
    text = text.lower()

    # 精确匹配
    if keyword == text:
        return 100

    # 前缀匹配
    if text.startswith(keyword):
        return 80 + (len(keyword) / len(text)) * 10

    # 包含匹配
    if keyword in text:
        return 60 + (len(keyword) / len(text)) * 10

    # 编辑距离匹配（简化版）
    distance = _levenshtein_distance(keyword, text)
    max_len = max(len(keyword), len(text))
    similarity = 1 - (distance / max_len)

    if similarity > 0.5:
        return int(similarity * 40)

    return 0


def _levenshtein_distance(s1: str, s2: str) -> int:
    """计算两个字符串的编辑距离。"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]
