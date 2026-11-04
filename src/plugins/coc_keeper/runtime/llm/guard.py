"""叙事守卫：模型写出来的东西，发出去之前过一遍。

三类检查（全部 fail-closed）：
- 剧透：与未发现线索 / keeper_text 共享任意 6 字片段
- 规则泄漏：出现骰点、检定、目标值、大成功这类元叙述
- 长度：超过上限（QQ 群聊里太长会刷屏）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 骰点/规则字样：叙事里不该出现
_RULE_RE = re.compile(
    r"\b\d{1,3}\s*/\s*\d{1,3}\b"      # 77/25
    r"|\bd\d{1,3}\b"                   # d100
    r"|检定|骰子|骰点|目标值|大成功|大失败|成功率",
    re.IGNORECASE,
)

MAX_CHARS = 600


@dataclass
class GuardResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def _ngrams(text: str, n: int = 6) -> set[str]:
    clean = re.sub(r"\s+", "", text)
    if len(clean) < n:
        return {clean} if clean else set()
    return {clean[i:i + n] for i in range(len(clean) - n + 1)}


def leaks(text: str, secrets: list[str] | tuple[str, ...]) -> bool:
    """与任一秘密共享 6 字片段即视为泄漏。"""
    text_grams = _ngrams(text)
    if not text_grams:
        return False
    for secret in secrets or ():
        if secret and text_grams & _ngrams(secret):
            return True
    return False


def check(text: str, *, secrets: list[str] | tuple[str, ...] = (), max_chars: int = MAX_CHARS) -> GuardResult:
    reasons: list[str] = []
    body = (text or "").strip()
    if not body:
        return GuardResult(ok=False, reasons=["空文本"])
    if len(body) > max_chars:
        reasons.append(f"超长({len(body)}字)")
    if _RULE_RE.search(body):
        reasons.append("出现规则/骰点字样")
    if leaks(body, secrets):
        reasons.append("疑似剧透")
    return GuardResult(ok=not reasons, reasons=reasons)
