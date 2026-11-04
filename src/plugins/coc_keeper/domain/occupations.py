"""职业数据：本职技能、技能点公式、信用评级、属性模板（CoC 7e）。

数值约定：
- 属性模板用于「点数分配」模式：8 项，每项 40-90，合计恰好 460
- 技能点：本职 = 职业公式（多数 EDU×4），兴趣 = INT×2
- 信用评级是本职技能之一，取值范围由职业决定
"""

from __future__ import annotations

from dataclasses import dataclass

from .character import ATTRS, default_skills

POINT_BUY_TOTAL = 460
POINT_BUY_MIN = 40
POINT_BUY_MAX = 90
CREATION_SKILL_CAP = 90

# 7e 里不在基础表、但有固定起始值的专业技能
SPECIAL_SKILL_BASE: dict[str, int] = {
    "医学": 1,
    "药学": 1,
    "生物学": 1,
    "化学": 1,
    "法律": 5,
    "估价": 5,
    "乔装": 5,
    "摄影": 5,
    "艺术(文学)": 5,
    "计算机使用": 5,
    "电子学": 1,
    "机械维修": 10,
    "信用评级": 0,
}


@dataclass(frozen=True)
class Occupation:
    key: str
    name: str
    aliases: tuple[str, ...]
    skills: tuple[str, ...]          # 本职技能（含「信用评级」）
    skill_formula: str               # 例："edu*4" / "edu*2+dex*2"
    credit_range: tuple[int, int]    # 信用评级下限/上限
    template: dict                   # 属性模板，合计 460
    notes: str = ""

    def template_attrs(self) -> dict:
        return dict(self.template)


OCCUPATIONS: dict[str, Occupation] = {
    "reporter": Occupation(
        key="reporter", name="记者", aliases=("记者", "新闻记者", "reporter"),
        skills=("摄影", "历史", "图书馆使用", "心理学", "侦查", "话术", "母语", "信用评级"),
        skill_formula="edu*4", credit_range=(10, 40),
        template={"STR": 50, "CON": 50, "SIZ": 50, "DEX": 55, "APP": 60, "INT": 70, "POW": 55, "EDU": 70},
        notes="靠嘴和眼睛吃饭：侦查/话术优先。",
    ),
    "detective": Occupation(
        key="detective", name="私家侦探", aliases=("私家侦探", "侦探", "detective"),
        skills=("乔装", "法律", "图书馆使用", "心理学", "侦查", "话术", "潜行", "信用评级"),
        skill_formula="edu*2+dex*2", credit_range=(20, 50),
        template={"STR": 55, "CON": 55, "SIZ": 55, "DEX": 60, "APP": 50, "INT": 65, "POW": 60, "EDU": 60},
        notes="跟踪与套话；别正面硬拼。",
    ),
    "doctor": Occupation(
        key="doctor", name="医生", aliases=("医生", "医师", "doctor"),
        skills=("医学", "急救", "心理学", "生物学", "化学", "药学", "侦查", "图书馆使用", "信用评级"),
        skill_formula="edu*4", credit_range=(40, 90),
        template={"STR": 50, "CON": 55, "SIZ": 50, "DEX": 60, "APP": 50, "INT": 65, "POW": 55, "EDU": 75},
        notes="医学与急救是硬通货；侦查别落下。",
    ),
    "professor": Occupation(
        key="professor", name="教授", aliases=("教授", "学者", "professor"),
        skills=("图书馆使用", "心理学", "历史", "神秘学", "母语", "信用评级"),
        skill_formula="edu*4", credit_range=(40, 90),
        template={"STR": 45, "CON": 50, "SIZ": 50, "DEX": 50, "APP": 50, "INT": 75, "POW": 55, "EDU": 85},
        notes="知识型；遇到危险要有人护着。",
    ),
    "antiquarian": Occupation(
        key="antiquarian", name="古董商", aliases=("古董商", "古董", "antiquarian"),
        skills=("估价", "历史", "图书馆使用", "侦查", "话术", "会计", "信用评级"),
        skill_formula="edu*4", credit_range=(30, 70),
        template={"STR": 45, "CON": 50, "SIZ": 50, "DEX": 55, "APP": 55, "INT": 65, "POW": 60, "EDU": 80},
        notes="识货、识人；对旧物有直觉。",
    ),
    "police": Occupation(
        key="police", name="警探", aliases=("警探", "警察", "警官", "police"),
        skills=("射击(手枪)", "法律", "聆听", "心理学", "侦查", "话术", "恐吓", "信用评级"),
        skill_formula="edu*2+dex*2", credit_range=(20, 50),
        template={"STR": 60, "CON": 60, "SIZ": 60, "DEX": 60, "APP": 50, "INT": 60, "POW": 55, "EDU": 55},
        notes="能打能查；开火要付代价。",
    ),
    "writer": Occupation(
        key="writer", name="作家", aliases=("作家", "小说家", "writer"),
        skills=("艺术(文学)", "历史", "图书馆使用", "心理学", "母语", "神秘学", "信用评级"),
        skill_formula="edu*4", credit_range=(10, 40),
        template={"STR": 45, "CON": 50, "SIZ": 50, "DEX": 55, "APP": 55, "INT": 75, "POW": 60, "EDU": 70},
        notes="灵感与知识；身体是短板。",
    ),
    "nurse": Occupation(
        key="nurse", name="护士", aliases=("护士", "nurse"),
        skills=("急救", "医学", "聆听", "心理学", "生物学", "药学", "侦查", "信用评级"),
        skill_formula="edu*4", credit_range=(30, 60),
        template={"STR": 45, "CON": 55, "SIZ": 50, "DEX": 55, "APP": 55, "INT": 60, "POW": 55, "EDU": 85},
        notes="急救主力；比医生更常在一线。",
    ),
    "engineer": Occupation(
        key="engineer", name="工程师", aliases=("工程师", "engineer"),
        skills=("机械维修", "电子学", "计算机使用", "会计", "图书馆使用", "侦查", "信用评级"),
        skill_formula="edu*4", credit_range=(30, 70),
        template={"STR": 50, "CON": 55, "SIZ": 55, "DEX": 55, "APP": 45, "INT": 70, "POW": 50, "EDU": 80},
        notes="拆东西、修东西；实验室里最稳。",
    ),
}


def list_occupations() -> list[Occupation]:
    return list(OCCUPATIONS.values())


def get_occupation(key_or_name: str | None) -> Occupation | None:
    """按 key / 中文名 / 别名匹配职业（大小写不敏感）。"""
    text = (key_or_name or "").strip()
    if not text:
        return None
    lowered = text.lower()
    for occupation in OCCUPATIONS.values():
        if lowered == occupation.key.lower() or text == occupation.name:
            return occupation
        if any(lowered == alias.lower() for alias in occupation.aliases):
            return occupation
    return None


def skill_points(formula: str, attrs: dict) -> int:
    """解析技能点公式，如 ``edu*4`` / ``edu*2+dex*2``。"""
    total = 0
    for term in (formula or "").split("+"):
        term = term.strip().lower()
        if not term:
            continue
        if "*" in term:
            attr, multiplier = term.split("*", 1)
            key = attr.strip().upper()
            if key not in ATTRS:
                raise ValueError(f"未知属性: {attr!r}")
            total += int(attrs[key]) * int(multiplier)
        else:
            total += int(term)
    return total


def base_skill_value(name: str, attrs: dict) -> int:
    """技能起始值：基础表优先，其次专业技能表，最后 1。"""
    skills = default_skills(attrs)
    if name in skills:
        return int(skills[name])
    return int(SPECIAL_SKILL_BASE.get(name, 1))


def validate_occupations() -> list[str]:
    """数据自检：模板合计 460、单项 40-90、技能非空、信用评级合法。"""
    problems: list[str] = []
    seen_names: set[str] = set()
    for occupation in OCCUPATIONS.values():
        if occupation.name in seen_names:
            problems.append(f"职业重名: {occupation.name}")
        seen_names.add(occupation.name)

        missing = [key for key in ATTRS if key not in occupation.template]
        if missing:
            problems.append(f"{occupation.name} 模板缺属性: {missing}")
            continue
        total = sum(int(value) for value in occupation.template.values())
        if total != POINT_BUY_TOTAL:
            problems.append(f"{occupation.name} 模板合计 {total}，应为 {POINT_BUY_TOTAL}")
        for key in ATTRS:
            value = int(occupation.template[key])
            if not (POINT_BUY_MIN <= value <= POINT_BUY_MAX):
                problems.append(f"{occupation.name} 模板 {key}={value} 超出 {POINT_BUY_MIN}-{POINT_BUY_MAX}")

        if not occupation.skills:
            problems.append(f"{occupation.name} 没有本职技能")
        if "信用评级" not in occupation.skills:
            problems.append(f"{occupation.name} 本职技能缺少「信用评级」")
        low, high = occupation.credit_range
        if not (0 <= low <= high <= 99):
            problems.append(f"{occupation.name} 信用评级范围非法: {occupation.credit_range}")
        try:
            points = skill_points(occupation.skill_formula, occupation.template)
        except ValueError as exc:
            problems.append(f"{occupation.name} 技能点公式非法: {exc}")
            continue
        if points <= 0:
            problems.append(f"{occupation.name} 技能点公式结果非正: {points}")
    return problems
