"""角色创建校验：属性点数、技能池、创建上限、信用评级。

只负责「判断是否合法」，不做分配、不改数据；向导与导入共用这一个校验器。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .character import ATTRS, Investigator, validate as validate_sheet
from .occupations import (
    CREATION_SKILL_CAP,
    POINT_BUY_MAX,
    POINT_BUY_MIN,
    POINT_BUY_TOTAL,
    Occupation,
    base_skill_value,
    skill_points,
)

QUICK_MIN = 15
QUICK_MAX = 90


@dataclass
class CreationReport:
    ok: bool
    problems: list[str] = field(default_factory=list)
    mode: str = "point_buy"
    pool_occupation: int = 0
    pool_interest: int = 0
    spent_occupation: int = 0
    spent_interest: int = 0
    credit_rating: int | None = None

    @property
    def remaining_occupation(self) -> int:
        return self.pool_occupation - self.spent_occupation

    @property
    def remaining_interest(self) -> int:
        return self.pool_interest - self.spent_interest

    def summary(self) -> str:
        credit = f"{self.credit_rating}" if self.credit_rating is not None else "未分配"
        status = "通过" if self.ok else "未通过"
        return (
            f"{status}｜本职 {self.spent_occupation}/{self.pool_occupation}"
            f"（余 {self.remaining_occupation}）｜兴趣 {self.spent_interest}/{self.pool_interest}"
            f"（余 {self.remaining_interest}）｜信用评级 {credit}"
        )


def _check_attrs(attrs: dict, mode: str, problems: list[str]) -> None:
    missing = [key for key in ATTRS if key not in attrs]
    if missing:
        problems.append(f"缺少属性：{', '.join(missing)}")
        return

    values = {key: int(attrs[key]) for key in ATTRS}
    if mode == "quick":
        for key, value in values.items():
            if not (QUICK_MIN <= value <= QUICK_MAX) or value % 5 != 0:
                problems.append(f"{key}={value} 不符合快速骰点（{QUICK_MIN}-{QUICK_MAX}，5 的倍数）")
        return

    for key, value in values.items():
        if not (POINT_BUY_MIN <= value <= POINT_BUY_MAX):
            problems.append(f"{key}={value} 超出 {POINT_BUY_MIN}-{POINT_BUY_MAX}")
    total = sum(values.values())
    if total != POINT_BUY_TOTAL:
        diff = total - POINT_BUY_TOTAL
        problems.append(f"属性合计 {total}，需要正好 {POINT_BUY_TOTAL}（{'多' if diff > 0 else '少'} {abs(diff)}）")


def validate_creation(
    inv: Investigator,
    occupation: Occupation,
    *,
    mode: str = "point_buy",
    skill_cap: int = CREATION_SKILL_CAP,
) -> CreationReport:
    """校验一张新建角色卡是否满足规则与职业约束。

    Args:
        inv: 待校验角色卡（attrs 用 ×5 刻度）
        occupation: 职业
        mode: ``point_buy``（460/40-90）或 ``quick``（快速骰点）
        skill_cap: 创建时单项技能上限
    """
    problems: list[str] = []
    mode = mode if mode in ("point_buy", "quick") else "point_buy"

    _check_attrs(inv.attrs, mode, problems)

    attrs = {key: int(inv.attrs.get(key, 0)) for key in ATTRS}
    pool_occupation = skill_points(occupation.skill_formula, attrs)
    pool_interest = attrs.get("INT", 0) * 2

    occupation_skills = set(occupation.skills)
    spent_occupation = 0
    spent_interest = 0

    for name, raw_value in (inv.skills or {}).items():
        value = int(raw_value)
        if not (0 <= value <= 99):
            problems.append(f"技能 {name}={value} 超出 0-99")
            continue
        if value > skill_cap:
            problems.append(f"技能 {name}={value} 超过创建上限 {skill_cap}")
        if name == "母语":
            if value != attrs.get("EDU", 0):
                problems.append(f"母语应为 EDU={attrs.get('EDU', 0)}，当前 {value}")
            continue
        delta = max(0, value - base_skill_value(name, attrs))
        if name in occupation_skills:
            spent_occupation += delta
        else:
            spent_interest += delta

    if spent_occupation > pool_occupation:
        problems.append(f"本职技能点超支 {spent_occupation - pool_occupation}（池 {pool_occupation}）")
    if spent_interest > pool_interest:
        problems.append(f"兴趣技能点超支 {spent_interest - pool_interest}（池 {pool_interest}）")

    credit = int((inv.skills or {}).get("信用评级", 0))
    low, high = occupation.credit_range
    if credit < low or credit > high:
        problems.append(f"信用评级 {credit} 不在 {occupation.name} 的范围 {low}-{high} 内")

    problems.extend(validate_sheet(inv))

    return CreationReport(
        ok=not problems,
        problems=problems,
        mode=mode,
        pool_occupation=pool_occupation,
        pool_interest=pool_interest,
        spent_occupation=spent_occupation,
        spent_interest=spent_interest,
        credit_rating=credit,
    )
