"""P2 战斗 / 理智接线测试：/coc 攻击 与 /coc 理智 走 runtime。

固定骰子序列，避免不确定性。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_combat_runtime.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.plugins.coc_keeper.domain import Investigator, hp_max, mp_max, san_max  # noqa: E402
from src.plugins.coc_keeper.module import load_module  # noqa: E402
from src.plugins.coc_keeper.runtime import CocRuntime, TemplateNarrator  # noqa: E402
from src.plugins.coc_keeper.store.db import CocStore  # noqa: E402

MODULE_PATH = ROOT / "src" / "plugins" / "coc_keeper" / "data" / "modules" / "wugang.json"

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


def fixed_investigator() -> Investigator:
    attrs = {"STR": 30, "CON": 50, "SIZ": 30, "DEX": 60, "APP": 50, "INT": 60, "POW": 55, "EDU": 60}
    return Investigator(
        name="林医生",
        occupation="医生",
        attrs=attrs,
        skills={"斗殴": 60, "闪避": 40, "侦查": 65},
        state={"hp": hp_max(attrs), "mp": mp_max(attrs), "san": san_max(attrs), "luck": 50},
    )


async def main() -> None:
    module = load_module(MODULE_PATH)
    tmp = Path(tempfile.mkdtemp(prefix="coc_combat_rt_"))
    store = CocStore(tmp / "coc.sqlite3")
    module_id = store.save_module(module)
    campaign_id = store.create_campaign(module.title, group_id=527020285)
    store.set_campaign_module(campaign_id, module_id)
    char_id = store.save_character(campaign_id, fixed_investigator(), owner_qq=10001)

    # 攻击序列：攻击 05 命中 → 老陈闪避 99 失败 → 伤害 3 → 老陈反击 99 失败
    # 理智序列：SAN 检定 70 失败 → 损失 1d6=6 → 疯狂抽签 0（失忆）
    runtime = CocRuntime(store, TemplateNarrator(), SeqRng([5, 0, 9, 9, 3, 9, 9, 70, 6, 0]))
    await runtime.start(campaign_id, module_id)
    session_id = int(store.find_running_session(campaign_id)["id"])

    print("== 攻击 NPC ==")
    result = await runtime.attack(session_id, 10001, "老陈", "小刀")
    check("叙事含命中", "命中" in result.narrative or "伤害" in result.narrative, result.narrative[:80])
    state = store.get_session_state(session_id)
    npc = state.get("npc_hp", {}).get("dockhand", {})
    check("老陈 HP 从 11 降到 8", npc.get("hp") == 8, str(npc))
    check("玩家未受伤（反击失败）", store.get_character(char_id).hp == 8,
          str(store.get_character(char_id).hp))
    check("记了 combat_round 事件",
          any(e["type"] == "combat_round" for e in store.list_events(session_id, 20)))
    check("记了 combat 掷骰",
          any(r["kind"] == "combat" for r in store.list_rolls(session_id)))

    print("\n== 攻击不存在的目标 ==")
    miss = await runtime.attack(session_id, 10001, "张三")
    check("给出提示且不崩", "没有你要攻击的对象" in miss.narrative, miss.narrative[:60])

    print("\n== 理智检定 + 疯狂 ==")
    san_result = await runtime.sanity(session_id, 10001, "1/1d6")
    check("叙事含损失", "损失" in san_result.narrative, san_result.narrative[:80])
    check("叙事含疯狂症状", "失忆" in san_result.narrative, san_result.narrative[:80])
    loaded = store.get_character(char_id)
    check("SAN 从 55 降到 49", loaded.san == 49, str(loaded.san))
    state = store.get_session_state(session_id)
    check("累计损失已记录", state.get("san_loss_total") == 6, str(state.get("san_loss_total")))
    check("记了 san_check 事件",
          any(e["type"] == "san_check" for e in store.list_events(session_id, 30)))
    check("记了 san 掷骰",
          any(r["kind"] == "san" for r in store.list_rolls(session_id)))

    print("\n== 反复攻击直到倒下 ==")
    # 再打 3 次（每次伤害 3）：8 → 5 → 2 → 0
    for _ in range(3):
        await runtime.attack(session_id, 10001, "老陈", "小刀")
    state = store.get_session_state(session_id)
    npc = state.get("npc_hp", {}).get("dockhand", {})
    check("老陈倒下", npc.get("dead") is True and npc.get("hp") == 0, str(npc))
    again = await runtime.attack(session_id, 10001, "老陈", "小刀")
    check("倒下后不再结算", "已经倒下" in again.narrative, again.narrative[:60])

    store.close()
    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    print(f"（临时目录：{tmp}）")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
