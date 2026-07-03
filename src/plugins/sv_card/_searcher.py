# plugins/sv_card/_searcher.py
"""影之诗超凡世界 模糊搜索算法。

搜索优先级（已适配用户自制中文翻译数据）：
    1. 完整匹配（中文名完全相等）→ score = 100
    2. 完整匹配（日文名完全相等）→ score = 95
    3. 前缀匹配（中文名以关键词开头）→ score = 80
    4. 包含匹配（中文名包含关键词）→ score = 60
    5. 技能描述匹配（中文）→ score = 30
    6. 技能描述匹配（日文）→ score = 28
    7. 类型匹配 → score = 10

职业过滤：直接按 class_name 匹配
注意：不搜索 flavour_text（用户决定）
"""

from typing import Optional

from ._cache import CLASS_NAME_TO_CODE


def search_cards(
    keyword: str,
    cards: list[dict],
    class_filter_only: bool = False,
    limit: int = 10,
) -> list[dict]:
    """模糊搜索卡牌。"""
    if not keyword or not cards:
        return []

    # 多关键词（空格分隔，全部要匹配）
    keywords = keyword.lower().split()
    if not keywords:
        return []

    results: list[tuple[dict, int]] = []

    for card in cards:
        score = _calculate_score(card, keywords, class_filter_only)
        if score > 0:
            results.append((card, score))

    # 分数降序
    results.sort(key=lambda x: -x[1])

    # 去重（按 id）
    seen_ids: set[str] = set()
    unique_results: list[dict] = []
    for card, score in results:
        cid = card.get("id", "")
        if cid not in seen_ids:
            seen_ids.add(cid)
            unique_results.append(card)
            if len(unique_results) >= limit:
                break

    return unique_results


def _calculate_score(
    card: dict,
    keywords: list[str],
    class_filter_only: bool,
) -> int:
    """计算单张卡牌与关键词的匹配分数。"""
    if class_filter_only:
        return _calculate_class_score(card, keywords)

    total_score = 0
    name = (card.get("name") or "").lower()
    name_ja = (card.get("name_ja") or "").lower()
    skill_text = (card.get("skill_text") or "").lower()
    skill_text_ja = (card.get("skill_text_ja") or "").lower()
    type_name = (card.get("type_name") or "").lower()

    for keyword in keywords:
        keyword_score = 0

        # 1. 中文名完全相等
        if name == keyword:
            keyword_score = 100
        # 2. 日文名完全相等
        elif name_ja == keyword and name_ja:
            keyword_score = 95
        # 3. 中文名前缀匹配
        elif name.startswith(keyword) and name:
            keyword_score = 80
        # 4. 中文名包含
        elif keyword in name and name:
            keyword_score = 60
        # 5. 日文名包含（独立分支，因为 name_ja 通常不会 contains 走上面 4）
        elif name_ja and keyword in name_ja:
            keyword_score = 55
        # 6. 技能描述中文
        elif skill_text and keyword in skill_text:
            keyword_score = 30
        # 7. 技能描述日文
        elif skill_text_ja and keyword in skill_text_ja:
            keyword_score = 28
        # 8. 类型匹配
        elif type_name and keyword in type_name:
            keyword_score = 10

        if keyword_score == 0:
            return 0

        total_score += keyword_score

    return total_score


def _calculate_class_score(card: dict, keywords: list[str]) -> int:
    """计算职业过滤的匹配分数。"""
    class_name = card.get("class_name", "")

    for keyword in keywords:
        # 用别名表查 code
        target_code = CLASS_NAME_TO_CODE.get(keyword)
        if target_code is not None:
            if card.get("class_code") == target_code:
                return 100

        # 直接匹配 class_name
        if keyword == class_name:
            return 100

        # 兼容：英文职业名
        en_map = {
            "neutral": "中立",
            "forest": "精灵",
            "elf": "精灵",
            "sword": "皇家",
            "royal": "皇家",
            "rune": "法师",
            "witch": "法师",
            "dragon": "龙族",
            "abyss": "梦魇",
            "shadow": "梦魇",
            "vampire": "梦魇",
            "haven": "主教",
            "bishop": "主教",
            "portal": "超越者",
            "nemesis": "超越者",
        }
        if en_map.get(keyword.lower()) == class_name:
            return 100

    return 0


def fuzzy_match_score(keyword: str, text: str) -> int:
    """计算两个字符串的模糊匹配分数（编辑距离 + 前缀 + 包含）。"""
    if not keyword or not text:
        return 0

    keyword = keyword.lower()
    text = text.lower()

    if keyword == text:
        return 100
    if text.startswith(keyword):
        return 80 + (len(keyword) / len(text)) * 10
    if keyword in text:
        return 60 + (len(keyword) / len(text)) * 10

    distance = _levenshtein_distance(keyword, text)
    max_len = max(len(keyword), len(text))
    similarity = 1 - (distance / max_len)

    if similarity > 0.5:
        return int(similarity * 40)
    return 0


def _levenshtein_distance(s1: str, s2: str) -> int:
    """编辑距离。"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = current_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]
