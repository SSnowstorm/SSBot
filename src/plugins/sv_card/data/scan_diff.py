"""扫描 cards_cn_translated.json 中的繁简差异"""
import json
import zhconv
import sys
import io
from pathlib import Path

# Windows 终端 UTF-8 输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DATA_PATH = Path(r"E:\wzs\github-repo\SSBot\src\plugins\sv_card\data\cards_cn_translated.json")

with open(DATA_PATH, encoding="utf-8") as f:
    data = json.load(f)

# data 是 dict，key 是 card_id，value 是 card dict
cards = list(data.values())

# 统计：每个字段中繁→简的差异字符
diff_chars = {}  # {繁体字: [简体字, 出现次数]}
affected_cards = []  # 受影响的卡牌列表
field_stats = {"name": 0, "skill_text": 0, "evo_skill_text": 0}

for card in cards:
    card_affected = False
    for field in ("name", "skill_text", "evo_skill_text"):
        original = card.get(field, "") or ""
        if not original:
            continue
        simplified = zhconv.convert(original, "zh-cn")
        if original != simplified:
            field_stats[field] += 1
            card_affected = True
            # 找出具体哪些字符不同
            for o_char, s_char in zip(original, simplified):
                if o_char != s_char:
                    key = o_char
                    if key not in diff_chars:
                        diff_chars[key] = [s_char, 0]
                    diff_chars[key][1] += 1
    if card_affected:
        affected_cards.append(card.get("name", "") or card.get("name_ja", ""))

# 输出结果
print("=== 繁简差异字符统计 ===")
print(f"差异字符总数: {len(diff_chars)}")
for trad, (simp, count) in sorted(diff_chars.items(), key=lambda x: -x[1][1]):
    print(f"  {trad} -> {simp}  (出现 {count} 次)")

print()
print("=== 受影响字段统计 ===")
for field, count in field_stats.items():
    print(f"  {field}: {count} 张卡有差异")

print()
print(f"=== 受影响卡牌总数: {len(affected_cards)} / {len(cards)} ===")
print()
print("受影响卡牌名称（前30）:")
for name in affected_cards[:30]:
    s_name = zhconv.convert(name, "zh-cn")
    print(f"  {name} -> {s_name}")
if len(affected_cards) > 30:
    print(f"  ... 还有 {len(affected_cards) - 30} 张")
