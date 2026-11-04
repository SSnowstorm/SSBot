"""车卡数据与校验测试：职业数据、点买/快速骰点、技能池、信用评级。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_creation.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.plugins.coc_keeper.domain import (  # noqa: E402
    ATTRS,
    Investigator,
    POINT_BUY_TOTAL,
    base_skill_value,
    get_occupation,
    hp_max,
    list_occupations,
    mp_max,
    san_max,
    skill_points,
    validate_creation,
    validate_occupations,
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


def make_inv(attrs: dict, skills: dict) -> Investigator:
    return Investigator(
        name="测试调查员",
        occupation="医生",
        attrs=dict(attrs),
        skills=dict(skills),
        state={
            "hp": hp_max(attrs), "mp": mp_max(attrs), "san": san_max(attrs), "luck": 50,
        },
    )


def doctor(extra_attrs: dict | None = None, skills: dict | None = None) -> Investigator:
    attrs = get_occupation("医生").template_attrs()
    if extra_attrs:
        attrs.update(extra_attrs)
    return make_inv(attrs, skills or {})


def main() -> None:
    print("== 职业数据 ==")
    check("数据自检通过", validate_occupations() == [], str(validate_occupations()))
    occupations = list_occupations()
    check("至少 8 个职业", len(occupations) >= 8, str(len(occupations)))
    check("key 不重复", len({o.key for o in occupations}) == len(occupations))
    check("模板合计 460", all(sum(o.template.values()) == POINT_BUY_TOTAL for o in occupations))
    check("都有信用评级", all("信用评级" in o.skills for o in occupations))
    check("都有属性模板", all(set(o.template) == set(ATTRS) for o in occupations))

    print("\n== 职业查找 ==")
    check("按中文名", (get_occupation("医生") or None) is not None)
    check("按 key", (get_occupation("doctor") or None) is not None)
    check("按别名", get_occupation("医师").key == "doctor", str(get_occupation("医师")))
    check("空值返回 None", get_occupation("") is None)
    check("未知职业返回 None", get_occupation("魔法师") is None)

    print("\n== 公式与起始值 ==")
    check("edu*4", skill_points("edu*4", {"EDU": 70}) == 280)
    check("edu*2+dex*2", skill_points("edu*2+dex*2", {"EDU": 70, "DEX": 60}) == 260)
    try:
        skill_points("luck*4", {})
        check("未知属性报错", False)
    except ValueError:
        check("未知属性报错", True)
    attrs = get_occupation("医生").template_attrs()
    check("医学起始 1", base_skill_value("医学", attrs) == 1)
    check("急救起始 30", base_skill_value("急救", attrs) == 30)
    check("侦查起始 25", base_skill_value("侦查", attrs) == 25)

    print("\n== 合法医生卡 ==")
    inv = doctor(skills={"医学": 70, "急救": 60, "侦查": 60, "信用评级": 50, "母语": 75})
    report = validate_creation(inv, get_occupation("医生"))
    check("校验通过", report.ok, str(report.problems))
    check("本职池 300", report.pool_occupation == 300, str(report.pool_occupation))
    check("兴趣池 130", report.pool_interest == 130, str(report.pool_interest))
    check("信用评级 50", report.credit_rating == 50, str(report.credit_rating))
    check("剩余点为正", report.remaining_occupation >= 0, str(report.remaining_occupation))
    check("摘要可读", "本职" in report.summary() and "信用评级" in report.summary(), report.summary())

    print("\n== 属性校验 ==")
    over = doctor(extra_attrs={"STR": 60})
    report = validate_creation(over, get_occupation("医生"))
    check("合计超 460 被拦", any("合计" in p and "多" in p for p in report.problems), str(report.problems))

    high = doctor(extra_attrs={"STR": 95})
    report = validate_creation(high, get_occupation("医生"))
    check("单项超 90 被拦", any("STR=95" in p for p in report.problems), str(report.problems))

    quick_ok = doctor(skills={"信用评级": 50})
    report = validate_creation(quick_ok, get_occupation("医生"), mode="quick")
    check("快速模式接受 5 的倍数", report.ok, str(report.problems))

    quick_bad = doctor(extra_attrs={"STR": 47})
    report = validate_creation(quick_bad, get_occupation("医生"), mode="quick")
    check("快速模式拦截非 5 倍数", any("STR=47" in p for p in report.problems), str(report.problems))

    print("\n== 技能池 ==")
    spend = doctor(skills={"医学": 90, "急救": 90, "侦查": 90, "信用评级": 90})
    report = validate_creation(spend, get_occupation("医生"))
    check("本职超支被拦", any("本职技能点超支" in p for p in report.problems), str(report.problems))

    interest = doctor(skills={"斗殴": 90, "射击(手枪)": 90})
    report = validate_creation(interest, get_occupation("医生"))
    check("兴趣超支被拦", any("兴趣技能点超支" in p for p in report.problems), str(report.problems))

    capped = doctor(skills={"医学": 95})
    report = validate_creation(capped, get_occupation("医生"))
    check("创建上限 90 被拦", any("超过创建上限" in p for p in report.problems), str(report.problems))

    print("\n== 信用评级 ==")
    low = doctor(skills={"信用评级": 10})
    report = validate_creation(low, get_occupation("医生"))
    check("低于职业下限被拦", any("信用评级" in p for p in report.problems), str(report.problems))
    check("报告里信用评级为 10", report.credit_rating == 10, str(report.credit_rating))

    print("\n== 母语 ==")
    native = doctor(skills={"母语": 60})
    report = validate_creation(native, get_occupation("医生"))
    check("母语不等于 EDU 被拦", any("母语应为" in p for p in report.problems), str(report.problems))

    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
