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
    DamageResult,
    EffectError,
    SanResult,
    apply_damage,
    is_indefinite_insanity,
    parse_san_loss,
    sanity_check,
    stabilization_target,
    unconscious_check_target,
)

__all__ = [
    "ATTRS", "BASE_SKILLS", "Investigator", "damage_bonus", "default_skills",
    "hp_max", "movement", "mp_max", "random_investigator", "san_max", "validate",
    "OUTCOME_LABEL", "CheckResult", "Difficulty", "Outcome", "is_fumble", "opposed",
    "resolve", "target_value",
    "DiceError", "d100", "roll", "roll_damage",
    "DamageResult", "EffectError", "SanResult", "apply_damage",
    "is_indefinite_insanity", "parse_san_loss", "sanity_check",
    "stabilization_target", "unconscious_check_target",
]
