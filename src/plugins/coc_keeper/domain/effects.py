"""效果结算：理智（SAN）、伤害与重伤 / 濒死。

规则依据（CoC 7e）：
- SAN 检定：d100 ≤ 当前 SAN 成功；失败按模组给的 ``成功损失/失败损失`` 扣
- 单次损失 ≥ 5 → 需要一次 INT 检定决定是否「意识到自己疯了」（临时性疯狂）
- 累计损失 ≥ 初始 SAN 的 1/5 → 不定性疯狂
- 单次伤害 ≥ HP 上限的一半 → 重伤；HP ≤ 0 → 濒死
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from .dice import roll

_SAN_LOSS_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d*[dD]\d+|\d+)\s*$")


class EffectError(ValueError):
    """效果表达式非法。"""


# ---------------- SAN ----------------

@dataclass
class SanResult:
    expression: str
    roll: int
    success: bool
    loss: int
    san_before: int
    san_after: int
    sanity_check_ok: bool = True  # d100 ≤ 当前 SAN
    temp_insanity_check: bool = False  # 单次损失 ≥ 5，需要 INT 检定
    indefinite_insanity: bool = False  # 累计损失达到阈值

    def summary(self) -> str:
        return (
            f"SAN {self.roll}/{self.san_before} "
            f"{'成功' if self.success else '失败'} → 损失 {self.loss}，剩余 {self.san_after}"
        )


def parse_san_loss(expression: str) -> tuple[int, str]:
    """解析 ``1/1d6`` 形式的理智损失，返回 ``(成功损失, 失败表达式)``。"""
    match = _SAN_LOSS_RE.match(expression or "")
    if not match:
        raise EffectError(f"理智损失格式应为 成功/失败，例如 1/1d6，收到: {expression!r}")
    return int(match.group(1)), match.group(2)


def sanity_check(
    current_san: int,
    expression: str,
    rng: random.Random | None = None,
    *,
    initial_san: int | None = None,
    total_loss_before: int = 0,
) -> SanResult:
    """执行一次理智检定。

    Args:
        current_san: 当前 SAN
        expression: 模组给的损失，如 ``1/1d6``
        initial_san: 初始 SAN（用于判定不定性疯狂），默认等于 current_san
        total_loss_before: 此前累计损失（用于判定不定性疯狂）
    """
    rng = rng or random
    success_loss, fail_expr = parse_san_loss(expression)
    san_before = max(0, int(current_san))
    roll_value = rng.randint(1, 100)
    success = roll_value <= san_before

    if success:
        loss = min(success_loss, san_before)
    else:
        loss, _ = roll(fail_expr, rng)
        loss = min(loss, san_before)

    san_after = san_before - loss
    initial = san_before if initial_san is None else max(0, int(initial_san))
    total_after = max(0, int(total_loss_before)) + loss

    return SanResult(
        expression=expression,
        roll=roll_value,
        success=success,
        loss=loss,
        san_before=san_before,
        san_after=san_after,
        sanity_check_ok=success,
        temp_insanity_check=loss >= 5,
        indefinite_insanity=bool(initial) and total_after * 5 >= initial,
    )


def is_indefinite_insanity(initial_san: int, total_loss: int) -> bool:
    """累计损失是否达到不定性疯狂阈值（初始 SAN 的 1/5）。"""
    return bool(initial_san) and total_loss * 5 >= int(initial_san)


# ---------------- 伤害 ----------------

@dataclass
class DamageResult:
    damage: int
    hp_before: int
    hp_after: int
    major_wound: bool
    dying: bool
    unconscious: bool = False

    def summary(self) -> str:
        parts = [f"受到 {self.damage} 点伤害（HP {self.hp_before} → {self.hp_after}）"]
        if self.major_wound:
            parts.append("重伤")
        if self.dying:
            parts.append("濒死")
        return "，".join(parts)


def apply_damage(hp: int, hp_max: int, damage: int) -> DamageResult:
    """结算一次伤害；重伤阈值取 HP 上限的一半（向上取整）。"""
    hp_before = int(hp)
    damage = max(0, int(damage))
    hp_after = hp_before - damage
    threshold = max(1, (int(hp_max) + 1) // 2)
    return DamageResult(
        damage=damage,
        hp_before=hp_before,
        hp_after=hp_after,
        major_wound=damage >= threshold,
        dying=hp_after <= 0,
    )


def stabilization_target(con: int) -> int:
    """濒死时每轮 CON 检定的目标值。"""
    return max(1, int(con))


def unconscious_check_target(con: int) -> int:
    """重伤后避免昏迷的 CON 检定目标值。"""
    return max(1, int(con))
