"""骰子：d100（含奖励 / 惩罚骰）、通用骰表达式、伤害骰。

规则依据：CoC 7e —— 检定掷 d100；奖励骰额外掷十位骰并取更小，惩罚骰取更大。
所有函数接受可选的 ``rng``（``random.Random``），便于测试注入固定序列。
"""

from __future__ import annotations

import random
import re

# 奖励/惩罚骰的硬上限（规则通常最多 2 颗，留一点余量防止调用方传错）
MAX_EXTRA_DICE = 4

_DICE_RE = re.compile(r"^\s*(\d*)d(\d+)\s*(?:([+-])\s*(\d+))?\s*$", re.IGNORECASE)


class DiceError(ValueError):
    """骰子表达式非法。"""


def d100(
    rng: random.Random | None = None,
    *,
    bonus: int = 0,
    penalty: int = 0,
) -> tuple[int, dict]:
    """掷一次 d100，返回 ``(点数, 明细)``。

    奖励骰与惩罚骰按净值抵消（各 2 颗等价于 0 颗）。
    """
    rng = rng or random
    bonus = max(0, min(int(bonus), MAX_EXTRA_DICE))
    penalty = max(0, min(int(penalty), MAX_EXTRA_DICE))
    net = bonus - penalty
    extra = abs(net)

    units = rng.randint(0, 9)
    tens_rolls = [rng.randint(0, 9) for _ in range(1 + extra)]

    if net > 0:  # 奖励骰：取更小的十位
        tens = min(tens_rolls)
    elif net < 0:  # 惩罚骰：取更大的十位
        tens = max(tens_rolls)
    else:
        tens = tens_rolls[0]

    value = tens * 10 + units
    if value == 0:  # 00 + 0 视为 100
        value = 100

    detail = {
        "units": units,
        "tens": tens,
        "tens_rolls": tens_rolls,
        "bonus": bonus,
        "penalty": penalty,
        "net": net,
    }
    return value, detail


def roll(expression: str, rng: random.Random | None = None) -> tuple[int, list[int]]:
    """掷通用表达式，如 ``1d6``、``2d10+3``、``d8-1``。

    Returns:
        ``(总和, 每次点数列表)``
    """
    rng = rng or random
    match = _DICE_RE.match(expression or "")
    if not match:
        raise DiceError(f"非法骰子表达式: {expression!r}")

    count_text, sides_text, sign, modifier_text = match.groups()
    count = int(count_text) if count_text else 1
    sides = int(sides_text)
    if not (1 <= count <= 100):
        raise DiceError(f"骰子数量需在 1-100 之间: {expression!r}")
    if not (2 <= sides <= 1000):
        raise DiceError(f"骰子面数需在 2-1000 之间: {expression!r}")

    rolls = [rng.randint(1, sides) for _ in range(count)]
    total = sum(rolls)
    if modifier_text:
        modifier = int(modifier_text)
        total = total + modifier if sign == "+" else total - modifier
    return total, rolls


def roll_damage(
    expression: str,
    rng: random.Random | None = None,
    *,
    damage_bonus: int = 0,
) -> tuple[int, list[int]]:
    """掷伤害骰并叠加伤害加值（DB）。"""
    total, rolls = roll(expression, rng)
    total = max(0, total + int(damage_bonus))
    return total, rolls
