"""战斗：先攻、攻击检定、闪避对抗、伤害与重伤。

只做群聊跑团撑得住的粒度（设计文档 4.3）：
- 先攻按 DEX 降序
- 近战：攻击检定 → 目标可闪避（对抗）→ 命中才掷伤害
- 伤害：武器 + 伤害加值；单次 ≥ HP 上限一半即重伤，HP ≤ 0 濒死
- 不做部位/护甲耐久/载具
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .check import CheckResult, Difficulty, resolve
from .dice import roll
from .effects import apply_damage


@dataclass
class Weapon:
    name: str
    skill: str = "斗殴"
    damage: str = "1d3"
    applies_damage_bonus: bool = True


@dataclass
class AttackOutcome:
    hit: bool
    attack_check: CheckResult
    defense_check: CheckResult | None
    damage: int
    hp_before: int
    hp_after: int
    major_wound: bool
    dying: bool
    detail: dict

    def summary(self) -> str:
        if not self.hit:
            why = "被闪避" if self.defense_check and self.defense_check.success else "未命中"
            return f"攻击{why}（{self.attack_check.roll}/{self.attack_check.target}）"
        parts = [f"命中 {self.damage} 点伤害（HP {self.hp_before} → {self.hp_after}）"]
        if self.major_wound:
            parts.append("重伤")
        if self.dying:
            parts.append("濒死")
        return "，".join(parts)


def initiative_order(combatants: list[dict]) -> list[dict]:
    """按 DEX 降序排列；同值保持输入顺序。"""
    return sorted(combatants, key=lambda c: -int(c.get("DEX", 0)))


def resolve_attack(
    attacker_skill: int,
    *,
    weapon: Weapon | None = None,
    defender_dodge: int | None = None,
    hp: int = 10,
    hp_max: int = 10,
    damage_bonus: int = 0,
    bonus: int = 0,
    penalty: int = 0,
    rng: random.Random | None = None,
) -> AttackOutcome:
    """结算一次攻击。

    Args:
        attacker_skill: 攻击技能值（斗殴 / 射击…）
        weapon: 武器；默认徒手 1d3
        defender_dodge: 目标的闪避值；为 None 表示不闪避
        damage_bonus: 伤害加值（DB 的数值形态；DB 为骰子时由调用方先折算）
    """
    rng = rng or random
    weapon = weapon or Weapon("徒手", "斗殴", "1d3")

    attack_check = resolve(weapon.skill, attacker_skill, Difficulty.REGULAR, bonus=bonus, penalty=penalty, rng=rng)
    defense_check: CheckResult | None = None
    detail: dict = {"weapon": weapon.name}

    if not attack_check.success:
        return AttackOutcome(
            hit=False, attack_check=attack_check, defense_check=None, damage=0,
            hp_before=int(hp), hp_after=int(hp), major_wound=False, dying=False, detail=detail,
        )

    if defender_dodge is not None:
        defense_check = resolve("闪避", defender_dodge, Difficulty.REGULAR, rng=rng)
        # 战斗里「同级防守获胜」：闪避等级 ≥ 攻击等级就算躲开
        detail["defense_rank"] = defense_check.rank
        detail["attack_rank"] = attack_check.rank
        if defense_check.success and defense_check.rank >= attack_check.rank:
            return AttackOutcome(
                hit=False, attack_check=attack_check, defense_check=defense_check, damage=0,
                hp_before=int(hp), hp_after=int(hp), major_wound=False, dying=False, detail=detail,
            )

    damage, rolls = roll(weapon.damage, rng)
    if weapon.applies_damage_bonus:
        damage += max(0, int(damage_bonus))
    damage = max(0, damage)
    detail["damage_rolls"] = rolls

    hit = apply_damage(hp, hp_max, damage)
    return AttackOutcome(
        hit=True, attack_check=attack_check, defense_check=defense_check, damage=damage,
        hp_before=hit.hp_before, hp_after=hit.hp_after,
        major_wound=hit.major_wound, dying=hit.dying, detail=detail,
    )


WEAPONS = {
    "徒手": Weapon("徒手", "斗殴", "1d3"),
    "小刀": Weapon("小刀", "斗殴", "1d4"),
    "棍棒": Weapon("棍棒", "斗殴", "1d6"),
    "手枪": Weapon("手枪", "射击(手枪)", "1d10"),
    "猎枪": Weapon("猎枪", "射击(步枪/霰弹枪)", "2d6"),
}


def weapon_by_name(name: str) -> Weapon:
    return WEAPONS.get(name or "", WEAPONS["徒手"])
