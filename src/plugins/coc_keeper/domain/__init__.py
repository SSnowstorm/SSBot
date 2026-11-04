"""CoC 7e 规则内核（P0）。

只依赖标准库，不导入 NoneBot —— 便于单测，也方便以后复用到网页端。
"""

from .character import (
    ATTRS,
    BASE_SKILLS,
    Investigator,
    damage_bonus,
    default_skills,
    hp_max,
    movement,
    mp_max,
    random_investigator,
    san_max,
    validate,
)
from .combat import WEAPONS, AttackOutcome, Weapon, initiative_order, resolve_attack, weapon_by_name
from .creation import CreationReport, auto_allocate_skills, validate_creation
from .occupations import (
    CREATION_SKILL_CAP,
    OCCUPATIONS,
    POINT_BUY_MAX,
    POINT_BUY_MIN,
    POINT_BUY_TOTAL,
    Occupation,
    base_skill_value,
    get_occupation,
    list_occupations,
    skill_points,
    validate_occupations,
)
from .check import (
    OUTCOME_LABEL,
    CheckResult,
    Difficulty,
    Outcome,
    is_fumble,
    opposed,
    resolve,
    target_value,
)
from .dice import DiceError, d100, roll, roll_damage
from .effects import (
    INDEFINITE_MADNESS,
    TEMPORARY_MADNESS,
    DamageResult,
    EffectError,
    SanResult,
    apply_damage,
    is_indefinite_insanity,
    parse_san_loss,
    roll_indefinite_madness,
    roll_temporary_madness,
    sanity_check,
    stabilization_target,
    unconscious_check_target,
)

__all__ = [
    "ATTRS", "BASE_SKILLS", "Investigator", "damage_bonus", "default_skills",
    "hp_max", "movement", "mp_max", "random_investigator", "san_max", "validate",
    "OUTCOME_LABEL", "CheckResult", "Difficulty", "Outcome", "is_fumble", "opposed",
    "resolve", "target_value",
    "WEAPONS", "AttackOutcome", "Weapon", "initiative_order", "resolve_attack", "weapon_by_name",
    "CreationReport", "auto_allocate_skills", "validate_creation",
    "CREATION_SKILL_CAP", "OCCUPATIONS", "POINT_BUY_MAX", "POINT_BUY_MIN", "POINT_BUY_TOTAL",
    "Occupation", "base_skill_value", "get_occupation", "list_occupations", "skill_points",
    "validate_occupations",
    "DiceError", "d100", "roll", "roll_damage",
    "DamageResult", "EffectError", "SanResult", "apply_damage",
    "is_indefinite_insanity", "parse_san_loss", "sanity_check",
    "stabilization_target", "unconscious_check_target",
    "TEMPORARY_MADNESS", "INDEFINITE_MADNESS", "roll_temporary_madness", "roll_indefinite_madness",
]
