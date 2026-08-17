import re
_PREFIX = re.compile(
    r"^\s*(?:[/／\\]?(?:sv|SV|影之诗|查卡))\s*(.*)$",
    flags=re.IGNORECASE,
)

tests = [
    "/sv 中立",
    "/sv 龙",
    "sv 中立",
    "sv龙",
    "/sv 10124110",
    "查卡 中立",
    "影之诗 龙",
    "  /sv  Albert  ",
    "中立",
]
for t in tests:
    m = _PREFIX.match(t)
    if m:
        print(f"{t!r:30s} -> {m.group(1).strip()!r}")
    else:
        print(f"{t!r:30s} -> (no match, raw: {t!r})")
