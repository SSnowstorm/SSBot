"""车卡向导测试：自动分配、点买流程、改属性/技能、快速骰点、恢复与取消。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_wizard.py
"""

import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.plugins.coc_keeper.domain import (  # noqa: E402
    auto_allocate_skills,
    get_occupation,
    validate_creation,
)
from src.plugins.coc_keeper.runtime.wizard import CharacterWizard  # noqa: E402
from src.plugins.coc_keeper.store.db import CocStore  # noqa: E402

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


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="coc_wizard_"))
    store = CocStore(tmp / "coc.sqlite3")
    campaign_id = store.create_campaign("测试团", group_id=527020285)
    qq = 10001
    wizard = CharacterWizard(store, rng=random.Random(42))

    print("== 自动分配 ==")
    doctor = get_occupation("医生")
    skills = auto_allocate_skills(doctor.template_attrs(), doctor)
    from src.plugins.coc_keeper.domain import Investigator, hp_max, mp_max, san_max

    inv = Investigator(
        name="测试", occupation="医生", attrs=doctor.template_attrs(), skills=skills,
        state={
            "hp": hp_max(doctor.template_attrs()), "mp": mp_max(doctor.template_attrs()),
            "san": san_max(doctor.template_attrs()), "luck": 50,
        },
    )
    report = validate_creation(inv, doctor)
    check("自动分配合法", report.ok, str(report.problems))
    check("侦查 ≥ 60", skills.get("侦查", 0) >= 60, str(skills.get("侦查")))
    check("信用评级在范围内", 40 <= skills.get("信用评级", 0) <= 90, str(skills.get("信用评级")))
    check("母语 = EDU", skills.get("母语") == doctor.template_attrs()["EDU"])

    print("\n== 点买流程 ==")
    reply = wizard.start(campaign_id, qq, name="林医生")
    check("第 1 步：选方式", reply.step == "mode" and "点数" in reply.text, reply.text[:60])

    reply = wizard.handle(campaign_id, qq, "点数")
    check("第 2 步：选职业", reply.step == "occupation" and "医生" in reply.text, reply.text[:60])

    reply = wizard.handle(campaign_id, qq, "医生")
    check("第 3 步：属性模板", reply.step == "attributes" and "460" in reply.text, reply.text[:80])

    reply = wizard.handle(campaign_id, qq, "教育 -10")
    check("改属性后提示差额", "450" in reply.text and "少" in reply.text, reply.text[-60:])

    reply = wizard.handle(campaign_id, qq, "教育 +10")
    check("改回后合计 460", "460" in reply.text, reply.text[-60:])

    reply = wizard.handle(campaign_id, qq, "确认")
    check("第 4 步：技能", reply.step == "skills" and "本职" in reply.text, reply.text[:80])

    reply = wizard.handle(campaign_id, qq, "侦查 95")
    check("超上限被拒", reply.step == "skills" and "超过创建上限" in reply.text, reply.text[:100])

    reply = wizard.handle(campaign_id, qq, "确认")
    check("第 5 步：预览", reply.step == "preview" and "HP" in reply.text, reply.text[:80])

    reply = wizard.handle(campaign_id, qq, "确认")
    check("入库完成", reply.done and reply.step == "done" and reply.character_id, str(reply))
    found = store.find_character_by_owner(campaign_id, qq)
    check("角色已保存", found is not None)
    _, saved = found
    check("创建元数据：点买+医生", saved.creation.get("mode") == "point_buy" and saved.creation.get("occupation") == "doctor",
          str(saved.creation))
    check("草稿已清理", store.get_draft(campaign_id, qq) is None)

    print("\n== 恢复与取消 ==")
    reply = wizard.start(campaign_id, qq)
    check("已有角色会提示覆盖", "覆盖" in reply.text, reply.text[:40])
    reply = wizard.handle(campaign_id, qq, "点数")
    check("进入第 2 步", reply.step == "occupation")
    resumed = wizard.start(campaign_id, qq)
    check("再次 start 能续上", "继续上次" in resumed.text and resumed.step == "occupation", resumed.text[:40])

    reply = wizard.handle(campaign_id, qq, "取消")
    check("取消清空草稿", store.get_draft(campaign_id, qq) is None and reply.step == "none", str(reply))

    print("\n== 快速骰点 ==")
    quick_qq = 20002
    wizard.start(campaign_id, quick_qq, name="快枪手")
    reply = wizard.handle(campaign_id, quick_qq, "快速")
    check("进入职业选择", reply.step == "occupation")
    reply = wizard.handle(campaign_id, quick_qq, "1")
    check("快速模式给属性并允许重掷", reply.step == "attributes" and "重掷" in reply.text, reply.text[:60])
    attrs = store.get_draft(campaign_id, quick_qq)["payload"]["attrs"]
    check("属性都是 5 的倍数", all(v % 5 == 0 for v in attrs.values()), str(attrs))
    reply = wizard.handle(campaign_id, quick_qq, "确认")
    check("快速模式进入技能", reply.step == "skills", reply.text[:60])
    reply = wizard.handle(campaign_id, quick_qq, "确认")
    check("快速模式进入预览", reply.step == "preview", reply.text[:60])
    reply = wizard.handle(campaign_id, quick_qq, "确认")
    check("快速模式入库", reply.done, str(reply))
    _, quick_saved = store.find_character_by_owner(campaign_id, quick_qq)
    check("创建元数据：quick", quick_saved.creation.get("mode") == "quick", str(quick_saved.creation))

    print("\n== 随机路径 ==")
    random_qq = 30003
    wizard.start(campaign_id, random_qq)
    reply = wizard.handle(campaign_id, random_qq, "随机")
    check("随机直接完成", reply.done and "随机调查员" in reply.text, reply.text[:40])
    _, random_saved = store.find_character_by_owner(campaign_id, random_qq)
    check("随机卡也记来源", random_saved.creation.get("source") == "random", str(random_saved.creation))

    store.close()
    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
