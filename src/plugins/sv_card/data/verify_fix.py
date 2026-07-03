"""验证繁简转换修复：搜索「天宫」是否能命中"""
import json
import sys
import io
import zhconv
from pathlib import Path

# Windows UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DATA_PATH = Path(r"E:\wzs\github-repo\SSBot\src\plugins\sv_card\data\cards_cn_translated.json")
with open(DATA_PATH, encoding="utf-8") as f:
    raw_data = json.load(f)

# 模拟 _normalize_card 对 name 的处理
def normalize_name(raw_name):
    return zhconv.convert(raw_name, "zh-cn") if raw_name else ""

# 模拟 _calculate_score 的搜索逻辑（简化版，仅测 name 匹配）
keyword = "天宫".lower()
results = []

for k, v in raw_data.items():
    if k == "_meta" or not isinstance(v, dict):
        continue
    raw_name = v.get("name", "") or ""
    name_cn = normalize_name(raw_name)
    name_lower = name_cn.lower()

    score = 0
    if name_lower == keyword:
        score = 100
    elif name_lower.startswith(keyword):
        score = 80
    elif keyword in name_lower:
        score = 60

    if score > 0:
        results.append((name_cn, raw_name, score, v.get("card_id")))

results.sort(key=lambda x: -x[2])

print(f"搜索关键词: 「天宫」")
print(f"命中数量: {len(results)}")
print()
for cn_name, raw_name, score, cid in results:
    changed = "✅ 已转换" if cn_name != raw_name else "（无变化）"
    print(f"  [{score}分] {cn_name}  (原始: {raw_name}  {changed})  card_id={cid}")

# 再测几个常见繁体关键词
print()
print("=" * 40)
for kw in ["圣", "绝", "师", "术", "铁", "长"]:
    count = 0
    for k, v in raw_data.items():
        if k == "_meta" or not isinstance(v, dict):
            continue
        raw_name = v.get("name", "") or ""
        name_cn = normalize_name(raw_name)
        if kw in name_cn.lower():
            count += 1
    trad = zhconv.convert(kw, "zh-tw")  # 反向看繁体是什么
    print(f"搜索「{kw}」命中 {count} 张卡名  (繁体对应: {trad})")
