"""调查员角色卡：属性、派生值、默认技能、随机车卡与校验。

约定：``attrs`` 存 **×5 后的数值**（7e 的百分比刻度，例如 STR 55），
这样 ``HP = (CON+SIZ)/10``、``MP = POW/5`` 可以直接算，不用再乘。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

ATTRS = ("STR", "CON", "SIZ", "DEX", "APP", "INT", "POW", "EDU")

# 7e 基础技能值（未分配点数时的默认值）
BASE_SKILLS = {
    "侦查": 25,
    "聆听": 20,
    "图书馆使用": 20,
    "潜行": 20,
    "心理学": 10,
    "话术": 10,
    "魅惑": 15,
    "恐吓": 15,
    "斗殴": 25,
    "射击(手枪)": 20,
    "投掷": 20,
    "游泳": 20,
    "攀爬": 20,
    "跳跃": 20,
    "急救": 30,
    "历史": 5,
    "神秘学": 5,
    "会计": 5,
    "机械维修": 10,
    "驾驶(汽车)": 20,
}

OCCUPATIONS = ("记者", "私家侦探", "医生", "教授", "古董商", "警探", "作家")
RISK_NOTES = ("守秘人默认：本局使用 CoC 7e 基础规则，房规以开团公告为准。")


class CharacterError(ValueError):
    """角色卡数据非法。"""


def hp_max(attrs: dict) -> int:
    return max(1, (int(attrs["CON"]) + int(attrs["SIZ"])) // 10)


def mp_max(attrs: dict) -> int:
    return max(1, int(attrs["POW"]) // 5)


def san_max(attrs: dict) -> int:
    return min(99, int(attrs["POW"]))


def movement(attrs: dict) -> int:
    """MOV：DEX 与 STR 都低于 SIZ → 7；都高于 SIZ → 9；其余 8。"""
    dex, str_, siz = int(attrs["DEX"]), int(attrs["STR"]), int(attrs["SIZ"])
    if dex < siz and str_ < siz:
        return 7
    if dex > siz and str_ > siz:
        return 9
    return 8


def damage_bonus(attrs: dict) -> tuple[str, int]:
    """返回 ``(伤害加值表达式, 体格)``。"""
    total = int(attrs["STR"]) + int(attrs["SIZ"])
    if total < 65:
        return "0", 0
    if total < 85:
        return "-1", 1
    if total < 125:
        return "1d4", 2
    if total < 165:
        return "1d6", 3
    return "2d6", 4


def default_skills(attrs: dict) -> dict[str, int]:
    skills = dict(BASE_SKILLS)
    skills["闪避"] = int(attrs["DEX"]) // 2
    skills["母语"] = int(attrs["EDU"])
    return skills


@dataclass
class Investigator:
    """一张角色卡（PC 或简化 NPC 都能用）。"""

    name: str
    occupation: str = "记者"
    attrs: dict = field(default_factory=dict)
    skills: dict = field(default_factory=dict)
    public: dict = field(default_factory=dict)
    secret: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)
    creation: dict = field(default_factory=dict)

    # ---- 派生值 ----
    @property
    def hp_max(self) -> int:
        return hp_max(self.attrs)

    @property
    def mp_max(self) -> int:
        return mp_max(self.attrs)

    @property
    def san_max(self) -> int:
        return san_max(self.attrs)

    @property
    def hp(self) -> int:
        return int(self.state.get("hp", self.hp_max))

    @property
    def mp(self) -> int:
        return int(self.state.get("mp", self.mp_max))

    @property
    def san(self) -> int:
        return int(self.state.get("san", self.san_max))

    @property
    def luck(self) -> int:
        return int(self.state.get("luck", 50))

    # ---- 技能 ----
    def skill_value(self, name: str) -> int:
        """取技能值：已分配点数优先，否则回退默认值，再否则 1。"""
        if name in self.skills:
            return int(self.skills[name])
        return int(default_skills(self.attrs).get(name, 1))

    def effective_skills(self) -> dict[str, int]:
        merged = default_skills(self.attrs)
        merged.update({k: int(v) for k, v in self.skills.items()})
        return merged

    def apply_damage(self, amount: int) -> dict:
        """扣血并返回变化摘要（是否重伤 / 濒死）。"""
        before = self.hp
        after = before - max(0, int(amount))
        self.state["hp"] = max(-99, after)
        return {
            "hp_before": before,
            "hp_after": after,
            "damage": int(amount),
            "major_wound": int(amount) >= max(1, self.hp_max // 2),
            "dying": after <= 0,
        }

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "occupation": self.occupation,
            "attrs": dict(self.attrs),
            "skills": dict(self.skills),
            "public": dict(self.public),
            "secret": dict(self.secret),
            "state": {
                "hp": self.hp,
                "hp_max": self.hp_max,
                "mp": self.mp,
                "mp_max": self.mp_max,
                "san": self.san,
                "san_max": self.san_max,
                "luck": self.luck,
            },
            "creation": dict(self.creation),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Investigator":
        return cls(
            name=data.get("name") or "无名调查员",
            occupation=data.get("occupation") or "记者",
            attrs=dict(data.get("attrs") or {}),
            skills=dict(data.get("skills") or {}),
            public=dict(data.get("public") or {}),
            secret=dict(data.get("secret") or {}),
            state=dict(data.get("state") or {}),
            creation=dict(data.get("creation") or {}),
        )


def random_investigator(
    rng: random.Random | None = None,
    *,
    name: str = "无名调查员",
    occupation: str | None = None,
) -> Investigator:
    """随机车卡：STR/CON/DEX/APP/POW 3d6×5；SIZ/INT/EDU (2d6+6)×5。"""
    rng = rng or random

    def roll_3d6() -> int:
        return sum(rng.randint(1, 6) for _ in range(3)) * 5

    def roll_2d6p6() -> int:
        return (sum(rng.randint(1, 6) for _ in range(2)) + 6) * 5

    attrs = {
        "STR": roll_3d6(),
        "CON": roll_3d6(),
        "SIZ": roll_2d6p6(),
        "DEX": roll_3d6(),
        "APP": roll_3d6(),
        "INT": roll_2d6p6(),
        "POW": roll_3d6(),
        "EDU": roll_2d6p6(),
    }
    inv = Investigator(
        name=name,
        occupation=occupation or rng.choice(OCCUPATIONS),
        attrs=attrs,
        skills={},
        public={"背景": "匆匆赶到现场的调查员"},
    )
    inv.state = {
        "hp": inv.hp_max,
        "mp": inv.mp_max,
        "san": inv.san_max,
        "luck": roll_3d6(),
    }
    return inv


def validate(inv: Investigator) -> list[str]:
    """返回问题列表；空列表表示通过。"""
    problems: list[str] = []
    for key in ATTRS:
        if key not in inv.attrs:
            problems.append(f"缺少属性 {key}")
            continue
        value = inv.attrs[key]
        if not isinstance(value, int) or not (1 <= value <= 99):
            problems.append(f"属性 {key} 超出 1-99: {value!r}")

    for name, value in inv.skills.items():
        if not isinstance(value, int) or not (0 <= value <= 99):
            problems.append(f"技能 {name} 超出 0-99: {value!r}")

    if not (0 <= inv.hp <= inv.hp_max):
        problems.append(f"HP 超出 0-{inv.hp_max}: {inv.hp}")
    if not (0 <= inv.san <= inv.san_max):
        problems.append(f"SAN 超出 0-{inv.san_max}: {inv.san}")
    if not (0 <= inv.mp <= inv.mp_max):
        problems.append(f"MP 超出 0-{inv.mp_max}: {inv.mp}")
    return problems
