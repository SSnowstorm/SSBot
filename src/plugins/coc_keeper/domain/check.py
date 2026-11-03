"""技能检定：难度、目标值、成功等级、大成功 / 大失败、对抗检定。

规则依据：CoC 7e
- 目标值：常规 = 技能值；困难 = 技能值/2；极难 = 技能值/5（向下取整，最小 1）
- 大成功：默认仅 01（房规可切换为 ``≤ 目标值/5``）
- 大失败：技能 < 50 时 96-100；技能 ≥ 50 时 100
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

from .dice import d100


class Difficulty(str, Enum):
    REGULAR = "regular"
    HARD = "hard"
    EXTREME = "extreme"

    @classmethod
    def parse(cls, value: str | "Difficulty" | None) -> "Difficulty":
        if isinstance(value, Difficulty):
            return value
        text = str(value or "").strip().lower()
        mapping = {
            "": cls.REGULAR, "regular": cls.REGULAR, "常规": cls.REGULAR, "普通": cls.REGULAR,
            "hard": cls.HARD, "困难": cls.HARD,
            "extreme": cls.EXTREME, "极难": cls.EXTREME,
        }
        if text not in mapping:
            raise ValueError(f"未知难度: {value!r}")
        return mapping[text]


class Outcome(str, Enum):
    CRITICAL = "critical"      # 大成功
    EXTREME = "extreme"        # 极难成功
    HARD = "hard"              # 困难成功
    REGULAR = "regular"        # 常规成功
    FAILURE = "failure"        # 失败
    FUMBLE = "fumble"          # 大失败


OUTCOME_LABEL = {
    Outcome.CRITICAL: "大成功",
    Outcome.EXTREME: "极难成功",
    Outcome.HARD: "困难成功",
    Outcome.REGULAR: "成功",
    Outcome.FAILURE: "失败",
    Outcome.FUMBLE: "大失败",
}

# 对抗时比较成功等级
_RANK = {
    Outcome.FUMBLE: 0,
    Outcome.FAILURE: 1,
    Outcome.REGULAR: 2,
    Outcome.HARD: 3,
    Outcome.EXTREME: 4,
    Outcome.CRITICAL: 5,
}

_DIVISOR = {Difficulty.REGULAR: 1, Difficulty.HARD: 2, Difficulty.EXTREME: 5}


@dataclass
class CheckResult:
    """一次检定的完整结果（可直接落 roll 表）。"""

    skill: str
    skill_value: int
    difficulty: Difficulty
    target: int
    roll: int
    outcome: Outcome
    bonus: int = 0
    penalty: int = 0
    detail: dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.outcome not in (Outcome.FAILURE, Outcome.FUMBLE)

    @property
    def rank(self) -> int:
        return _RANK[self.outcome]

    @property
    def label(self) -> str:
        return OUTCOME_LABEL[self.outcome]

    def summary(self) -> str:
        """一行式描述，例如 ``侦查 37/65 成功``。"""
        mod = ""
        if self.bonus:
            mod = f"（奖励骰×{self.bonus}）"
        elif self.penalty:
            mod = f"（惩罚骰×{self.penalty}）"
        return f"{self.skill} {self.roll}/{self.target} {self.label}{mod}"


def target_value(skill_value: int, difficulty: Difficulty | str = Difficulty.REGULAR) -> int:
    """按难度换算目标值。"""
    diff = Difficulty.parse(difficulty)
    return max(1, int(skill_value) // _DIVISOR[diff])


def is_fumble(roll: int, skill_value: int) -> bool:
    """大失败判定：技能 < 50 时 96-100；技能 ≥ 50 时 100。"""
    return roll == 100 or (int(skill_value) < 50 and roll >= 96)


def resolve(
    skill: str,
    skill_value: int,
    difficulty: Difficulty | str = Difficulty.REGULAR,
    *,
    bonus: int = 0,
    penalty: int = 0,
    critical_rule: str = "one",
    rng: random.Random | None = None,
) -> CheckResult:
    """执行一次技能检定。

    Args:
        skill: 技能名（仅用于展示与记录）
        skill_value: 技能值（0-99）
        difficulty: 常规 / 困难 / 极难
        bonus / penalty: 奖励骰 / 惩罚骰数量
        critical_rule: ``one``（仅 01 大成功，默认）/ ``fifth``（≤ 目标值/5 也算大成功）
    """
    diff = Difficulty.parse(difficulty)
    value = max(0, min(int(skill_value), 99))
    target = target_value(value, diff)
    roll_value, detail = d100(rng, bonus=bonus, penalty=penalty)

    if critical_rule == "fifth":
        is_critical = roll_value == 1 or roll_value <= max(1, value // 5)
    else:
        is_critical = roll_value == 1

    # 成功等级永远按「原始技能值」换算（极难 1/5、困难 1/2、常规 1/1），
    # 难度只决定「至少要达到哪一级才算成功」。
    extreme_threshold = max(1, value // 5)
    hard_threshold = max(1, value // 2)
    regular_threshold = max(1, value)

    if roll_value <= extreme_threshold:
        achieved = Outcome.EXTREME
    elif roll_value <= hard_threshold:
        achieved = Outcome.HARD
    elif roll_value <= regular_threshold:
        achieved = Outcome.REGULAR
    else:
        achieved = Outcome.FAILURE

    required = {
        Difficulty.REGULAR: Outcome.REGULAR,
        Difficulty.HARD: Outcome.HARD,
        Difficulty.EXTREME: Outcome.EXTREME,
    }[diff]

    if is_critical:
        outcome = Outcome.CRITICAL
    elif is_fumble(roll_value, value):
        outcome = Outcome.FUMBLE
    elif achieved is Outcome.FAILURE or _RANK[achieved] < _RANK[required]:
        outcome = Outcome.FAILURE
    else:
        outcome = achieved

    detail.update({"target": target, "critical_rule": critical_rule, "diff": diff.value})
    return CheckResult(
        skill=skill,
        skill_value=value,
        difficulty=diff,
        target=target,
        roll=roll_value,
        outcome=outcome,
        bonus=int(bonus),
        penalty=int(penalty),
        detail=detail,
    )


def opposed(a: CheckResult, b: CheckResult) -> str:
    """对抗检定：返回 ``"a"`` / ``"b"`` / ``"tie"``。

    先比成功等级；等级相同则比较技能值（高者胜）；仍相同才算平手。
    """
    if a.rank != b.rank:
        return "a" if a.rank > b.rank else "b"
    if a.skill_value != b.skill_value:
        return "a" if a.skill_value > b.skill_value else "b"
    return "tie"
