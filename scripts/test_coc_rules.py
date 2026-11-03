"""P0 规则内核单测（不启动 NoneBot、不连数据库）。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_rules.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.plugins.coc_keeper.domain import (  # noqa: E402
    Investigator,
    apply_damage,
    d100,
    damage_bonus,
    hp_max,
    is_fumble,
    movement,
    mp_max,
    opposed,
    parse_san_loss,
    random_investigator,
    resolve,
    roll,
    sanity_check,
    target_value,
    validate,
)
from src.plugins.coc_keeper.domain.check import Difficulty, Outcome  # noqa: E402

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


class Rigged:
    """按预设序列返回 randint 的假随机源。"""

    def __init__(self, values):
        self.values = list(values)

    def randint(self, a, b):
        return self.values.pop(0)


# ---------------- 骰子 ----------------

def test_dice() -> None:
    print("\n== 骰子 ==")
    # d100: 先取个位，再取十位
    value, detail = d100(Rigged([7, 5]))
    check("d100 基本组合 57", value == 57, f"got {value}")
    check("d100 明细含十位/个位", detail["tens"] == 5 and detail["units"] == 7)

    value, _ = d100(Rigged([0, 0]))
    check("00+0 视为 100", value == 100, f"got {value}")

    # 奖励骰：十位取更小；个位 7，十位 [9,0] → 07
    value, detail = d100(Rigged([7, 9, 0]), bonus=1)
    check("奖励骰取更小十位 → 7", value == 7, f"got {value} detail={detail}")
    # 惩罚骰：十位取更大；个位 7，十位 [1,9] → 97
    value, _ = d100(Rigged([7, 1, 9]), penalty=1)
    check("惩罚骰取更大十位 → 97", value == 97, f"got {value}")
    # 奖励与惩罚抵消
    value, detail = d100(Rigged([7, 4]), bonus=1, penalty=1)
    check("奖励惩罚抵消 → 47", value == 47 and detail["net"] == 0, f"got {value}")

    total, rolls = roll("2d6+3", Rigged([2, 3]))
    check("表达式 2d6+3 = 8", total == 8 and rolls == [2, 3], f"got {total} {rolls}")
    total, _ = roll("d8-1", Rigged([1]))
    check("表达式 d8-1 = 0", total == 0, f"got {total}")
    try:
        roll("2d")
        check("非法表达式抛错", False)
    except Exception:
        check("非法表达式抛错", True)


# ---------------- 检定 ----------------

def _forced(skill: int, roll_value: int, difficulty=Difficulty.REGULAR):
    tens, units = divmod(roll_value, 10)
    if roll_value == 100:
        tens, units = 0, 0
    return resolve("侦查", skill, difficulty, rng=Rigged([units, tens]))


def test_check() -> None:
    print("\n== 检定 ==")
    check("目标值 常规 65", target_value(65, Difficulty.REGULAR) == 65)
    check("目标值 困难 65→32", target_value(65, Difficulty.HARD) == 32)
    check("目标值 极难 65→13", target_value(65, Difficulty.EXTREME) == 13)
    check("目标值下限为 1", target_value(5, Difficulty.EXTREME) == 1)

    r = _forced(65, 1)
    check("掷出 01 大成功", r.outcome is Outcome.CRITICAL and r.success, r.label)
    r = _forced(65, 100)
    check("掷出 100 大失败", r.outcome is Outcome.FUMBLE, r.label)

    check("技能 40 时 96 大失败", is_fumble(96, 40))
    check("技能 60 时 96 只是失败", not is_fumble(96, 60))
    check("技能 60 时 100 大失败", is_fumble(100, 60))

    r = _forced(65, 12)
    check("12 ≤ 13 → 极难成功", r.outcome is Outcome.EXTREME, r.label)
    r = _forced(65, 30)
    check("30 ≤ 32 → 困难成功", r.outcome is Outcome.HARD, r.label)
    r = _forced(65, 60)
    check("60 ≤ 65 → 常规成功", r.outcome is Outcome.REGULAR, r.label)
    r = _forced(65, 66)
    check("66 > 65 → 失败", r.outcome is Outcome.FAILURE, r.label)

    # 困难难度：目标 32
    r = _forced(65, 35, Difficulty.HARD)
    check("困难难度 35 > 32 → 失败", r.outcome is Outcome.FAILURE, r.label)
    r = _forced(65, 30, Difficulty.HARD)
    check("困难难度 30 ≤ 32 → 困难成功", r.outcome is Outcome.HARD, r.label)

    # 对抗：等级高者胜；同级比技能值
    a = _forced(70, 30)   # 困难成功
    b = _forced(50, 40)   # 常规成功
    check("对抗：等级高者胜", opposed(a, b) == "a")
    c = _forced(70, 60)   # 常规成功（70）
    d = _forced(50, 40)   # 常规成功（50）
    check("对抗：同级技能值高者胜", opposed(c, d) == "a")


# ---------------- 角色卡 ----------------

def test_character() -> None:
    print("\n== 角色卡 ==")
    attrs = {"STR": 60, "CON": 55, "SIZ": 65, "DEX": 60, "APP": 50, "INT": 70, "POW": 50, "EDU": 70}
    check("HP = (CON+SIZ)/10 = 12", hp_max(attrs) == 12, str(hp_max(attrs)))
    check("MP = POW/5 = 10", mp_max(attrs) == 10, str(mp_max(attrs)))
    check("MOV：DEX<SIZ 且 STR<SIZ → 7", movement({"STR": 40, "SIZ": 70, "DEX": 50}) == 7)
    check("MOV：都高于 SIZ → 9", movement({"STR": 80, "SIZ": 60, "DEX": 70}) == 9)
    check("MOV：其余 → 8", movement({"STR": 60, "SIZ": 60, "DEX": 60}) == 8)

    db_text, build = damage_bonus({"STR": 60, "SIZ": 65})
    check("STR+SIZ=125 → DB 1d6 / 体格 3", (db_text, build) == ("1d6", 3), f"{db_text} {build}")
    db_text, _ = damage_bonus({"STR": 30, "SIZ": 30})
    check("STR+SIZ=60 → DB 0", db_text == "0")

    inv = random_investigator(name="测试员")
    check("随机车卡属性在 5-90", all(5 <= v <= 90 for v in inv.attrs.values()), str(inv.attrs))
    check("随机车卡 HP/MP/SAN 已初始化", inv.hp > 0 and inv.mp > 0 and inv.san > 0)
    check("随机车卡校验通过", validate(inv) == [], str(validate(inv)))
    check("默认技能：侦查 25", inv.skill_value("侦查") == 25)
    check("闪避默认 = DEX/2", inv.skill_value("闪避") == inv.attrs["DEX"] // 2)

    inv.skills["侦查"] = 70
    check("已分配点数覆盖默认值", inv.skill_value("侦查") == 70)

    bad = Investigator(name="坏卡", attrs={"STR": 999, "CON": 55, "SIZ": 65, "DEX": 60,
                                          "APP": 50, "INT": 70, "POW": 50, "EDU": 70})
    check("非法属性被检出", any("STR" in p for p in validate(bad)), str(validate(bad)))


# ---------------- SAN / 伤害 ----------------

def test_effects() -> None:
    print("\n== SAN 与伤害 ==")
    check("解析 1/1d6", parse_san_loss("1/1d6") == (1, "1d6"))
    check("解析 2/1d10", parse_san_loss("2/1d10") == (2, "1d10"))

    # 成功：d100 ≤ SAN
    ok = sanity_check(50, "1/1d6", Rigged([30, 2]))  # 30 成功；损失 1
    check("SAN 成功只损失最小值", ok.success and ok.loss == 1 and ok.san_after == 49,
          f"{ok.success} {ok.loss} {ok.san_after}")

    # 失败：d100 > SAN，损失 1d6
    bad = sanity_check(30, "1/1d4", Rigged([70, 3]))  # 70 失败；1d4=3
    check("SAN 失败损失掷骰值", (not bad.success) and bad.loss == 3, f"{bad.loss}")

    big = sanity_check(60, "1/1d10", Rigged([70, 6]))
    check("单次损失 ≥5 触发临时疯狂检定", big.temp_insanity_check and big.loss == 6, str(big.loss))

    ind = sanity_check(40, "1/1d6", Rigged([70, 6]), initial_san=40, total_loss_before=3)
    check("累计损失达 1/5 触发不定性疯狂", ind.indefinite_insanity, str(ind))

    low = sanity_check(2, "1/1d6", Rigged([70, 6]))
    check("SAN 不会扣成负数", low.san_after == 0, str(low.san_after))

    hurt = apply_damage(12, 12, 6)
    check("伤害 6/12 → 重伤", hurt.major_wound and not hurt.dying, str(hurt))
    hurt = apply_damage(5, 12, 5)
    check("HP 归零 → 濒死", hurt.dying and hurt.hp_after == 0)
    hurt = apply_damage(12, 12, 3)
    check("伤害 3 < 一半 → 不算重伤", not hurt.major_wound)


def main() -> None:
    test_dice()
    test_check()
    test_character()
    test_effects()
    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
