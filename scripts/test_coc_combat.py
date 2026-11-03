"""P2 战斗与疯狂表单测。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_combat.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.plugins.coc_keeper.domain import (  # noqa: E402
    INDEFINITE_MADNESS,
    TEMPORARY_MADNESS,
    initiative_order,
    resolve_attack,
    roll_indefinite_madness,
    roll_temporary_madness,
    weapon_by_name,
)

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK  {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


class SeqRng:
    def __init__(self, values):
        self.values = list(values)
        self.index = 0

    def randint(self, a, b):
        value = self.values[self.index % len(self.values)]
        self.index += 1
        return value


def test_initiative() -> None:
    print("\n== 先攻 ==")
    order = initiative_order([{"name": "A", "DEX": 50}, {"name": "B", "DEX": 70}, {"name": "C", "DEX": 60}])
    check("按 DEX 降序", [c["name"] for c in order] == ["B", "C", "A"], str(order))
    same = initiative_order([{"name": "A", "DEX": 50}, {"name": "B", "DEX": 50}])
    check("同 DEX 保持输入顺序", [c["name"] for c in same] == ["A", "B"])


def test_attack() -> None:
    print("\n== 攻击 ==")
    # 05 命中（60 技能），伤害 1d3=2
    hit = resolve_attack(60, weapon=weapon_by_name("小刀"), hp=10, hp_max=10, rng=SeqRng([5, 0, 2]))
    check("命中", hit.hit and hit.damage == 2, hit.summary())
    check("扣血正确", hit.hp_after == 8, str(hit.hp_after))
    check("未达重伤阈值", not hit.major_wound)

    miss = resolve_attack(60, rng=SeqRng([9, 9]))
    check("99 > 60 未命中", not miss.hit and miss.damage == 0, miss.summary())

    # 攻击 05（常规成功），闪避 03（常规成功）→ 同级防守获胜 → 躲开
    dodged = resolve_attack(60, defender_dodge=50, rng=SeqRng([5, 0, 3, 0]))
    check("同级闪避成功 → 躲开", not dodged.hit and dodged.defense_check is not None, dodged.summary())

    # 攻击大成功（01），闪避常规 → 命中
    crit = resolve_attack(60, defender_dodge=50, weapon=weapon_by_name("手枪"),
                          rng=SeqRng([1, 0, 3, 0, 7]))
    check("攻击等级高于闪避 → 命中", crit.hit and crit.damage == 7, crit.summary())

    # 重伤 / 濒死
    deadly = resolve_attack(60, weapon=weapon_by_name("猎枪"), hp=5, hp_max=12,
                            rng=SeqRng([5, 0, 4, 5]))
    check("单次伤害 ≥ 一半上限 → 重伤", deadly.major_wound, deadly.summary())
    check("HP 归零 → 濒死", deadly.dying and deadly.hp_after <= 0, str(deadly.hp_after))


def test_madness() -> None:
    print("\n== 疯狂表 ==")
    temp = roll_temporary_madness(SeqRng([0]))
    check("临时疯狂返回表内条目", temp["name"] == TEMPORARY_MADNESS[0][0] and temp["kind"] == "temporary", str(temp))
    check("带描述", bool(temp.get("desc")), str(temp))

    forever = roll_indefinite_madness(SeqRng([1]))
    check("不定性疯狂返回表内条目", forever["name"] == INDEFINITE_MADNESS[1][0], str(forever))

    names = {item[0] for item in TEMPORARY_MADNESS}
    check("临时表非空且不重复", len(TEMPORARY_MADNESS) >= 8 and len(names) == len(TEMPORARY_MADNESS),
          str(len(TEMPORARY_MADNESS)))


def main() -> None:
    test_initiative()
    test_attack()
    test_madness()
    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
