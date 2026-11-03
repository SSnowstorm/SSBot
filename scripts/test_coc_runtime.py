"""P1 运行时单测：模组加载 → 开局 → 调查/交谈/移动 → 结局 → 重开校验。

不联网（用 TemplateNarrator），骰子用固定序列，结果可复现。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_runtime.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.plugins.coc_keeper.domain import random_investigator  # noqa: E402
from src.plugins.coc_keeper.module import load_module, validate_module  # noqa: E402
from src.plugins.coc_keeper.runtime import CocRuntime, TemplateNarrator, parse_action  # noqa: E402
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
    """固定序列随机源：d100 先取个位再取十位。"""

    def __init__(self, values):
        self.values = list(values)
        self.index = 0

    def randint(self, a, b):
        value = self.values[self.index % len(self.values)]
        self.index += 1
        return value


async def main() -> None:
    print("== 模组加载 ==")
    module = load_module(MODULE_PATH)
    check("标题正确", module.title == "雾港的来信", module.title)
    check("3 个场景", len(module.scenes) == 3, str(list(module.scenes)))
    check("5 条线索", len(module.clues) == 5, str(list(module.clues)))
    check("2 个 NPC", len(module.npcs) == 2, str(list(module.npcs)))
    check("2 个结局", len(module.endings) == 2)
    check("起始场景 harbor", module.first_scene == "harbor")
    check("结构校验通过", validate_module(module.meta and {
        "meta": module.meta,
        "scenes": [
            {"id": s.id, "title": s.title, "player_text": s.player_text,
             "clues": s.clues, "npcs": s.npcs,
             "exits": [{"to": e.to, "label": e.label, "condition": e.condition} for e in s.exits]}
            for s in module.scenes.values()
        ],
        "clues": [
            {"id": c.id, "scene": c.scene, "name": c.name, "player_text": c.player_text,
             "discover_condition": c.discover_condition}
            for c in module.clues.values()
        ],
        "npcs": [{"id": n.id, "name": n.name} for n in module.npcs.values()],
        "endings": module.endings,
    }) == [])

    print("\n== 动作解析 ==")
    action = parse_action("我搜查那封信", clues=["湿透的信"])
    check("侦查动作被识别", action.type == "investigate" and "信" in action.target, str(action))
    action = parse_action("我和老陈说话", npcs=["老陈"])
    check("交谈动作被识别", action.type == "talk" and action.target == "老陈", str(action))
    action = parse_action("我去废弃仓库", exits=["去废弃仓库"])
    check("移动动作被识别", action.type == "move", str(action))
    action = parse_action("随便走走看")
    check("无法识别 → custom（调用方应反问）", action.type == "custom", str(action))

    print("\n== 开局与场景 ==")
    tmp = Path(tempfile.mkdtemp(prefix="coc_runtime_"))
    store = CocStore(tmp / "coc.sqlite3")
    store.save_module(module)
    module_row = store.find_module_by_title(module.title)
    campaign_id = store.create_campaign(module.title, group_id=527020285)
    store.set_campaign_module(campaign_id, int(module_row["id"]))

    inv = random_investigator(name="林医生")
    store.save_character(campaign_id, inv, owner_qq=10001)

    runtime = CocRuntime(store, TemplateNarrator(), SeqRng([5, 0]))  # 每次掷出 05
    result = await runtime.start(campaign_id, int(module_row["id"]))
    check("开局叙事含码头", "码头" in result.narrative, result.narrative[:60])
    check("场景为 harbor", result.state["scene"] == "harbor")
    session = store.find_running_session(campaign_id)
    check("会话已创建", session is not None)
    session_id = int(session["id"])

    print("\n== 条件出口（未拿线索 → 被挡） ==")
    blocked = await runtime.act(session_id, 10001, "我去废弃仓库")
    check("缺线索时移动被挡", "走不通" in blocked.narrative, blocked.narrative[:80])
    check("场景仍在 harbor", store.get_session_state(session_id)["scene"] == "harbor")

    print("\n== 交谈拿线索 ==")
    talk = await runtime.act(session_id, 10001, "我和老陈说话")
    check("交谈叙事含老陈或目击", ("老陈" in talk.narrative) or ("局长" in talk.narrative), talk.narrative[:80])
    check("dock_tip 已发现", store.has_clue(session_id, "dock_tip"))

    print("\n== 调查 + 检定 ==")
    inv_result = await runtime.act(session_id, 10001, "我检查那封信")
    check("检定结果存在且成功", inv_result.check is not None and inv_result.check.success,
          str(inv_result.check))
    check("发现 letter", store.has_clue(session_id, "letter"))
    check("叙事含信的内容", "别让灯灭" in inv_result.narrative, inv_result.narrative[:80])
    check("叙事不含 keeper 真相", "深潜者" not in inv_result.narrative, inv_result.narrative[:80])

    print("\n== 移动与第二场景 ==")
    moved = await runtime.act(session_id, 10001, "我去废弃仓库")
    check("已进入仓库", store.get_session_state(session_id)["scene"] == "warehouse",
          store.get_session_state(session_id)["scene"])
    check("仓库叙事含石灰或木箱", ("木箱" in moved.narrative) or ("石灰" in moved.narrative),
          moved.narrative[:80])

    crate = await runtime.act(session_id, 10001, "我搜查木箱")
    check("发现 crate", store.has_clue(session_id, "crate"), crate.narrative[:60])
    ledger = await runtime.act(session_id, 10001, "我查看账本")
    check("发现 ledger", store.has_clue(session_id, "ledger"), ledger.narrative[:60])

    print("\n== 结局 ==")
    await runtime.act(session_id, 10001, "我去灯塔")
    check("已进入灯塔", store.get_session_state(session_id)["scene"] == "lighthouse")
    ritual = await runtime.act(session_id, 10001, "我调查地上的符号")
    check("发现 ritual", store.has_clue(session_id, "ritual"), ritual.narrative[:60])

    ending = await runtime.act(session_id, 10001, "我用煤油泼向符号")
    check("触发结局并结束", ending.ended and ending.kind == "ending", str(ending.kind))
    check("结局叙事含火或港口", ("火" in ending.narrative) or ("港口" in ending.narrative),
          ending.narrative[:80])

    view = runtime.scene_view(session_id)
    check("scene_view 反映已结束", view.get("ended") == "burn", str(view.get("ended")))
    check("scene_view 统计线索数", len(view["clues"]) == 5, str(len(view["clues"])))

    after = await runtime.act(session_id, 10001, "我再找找")
    check("结束后再行动被拒绝", "已经结束" in after.narrative, after.narrative[:60])

    print("\n== 重开库校验 ==")
    store.close()
    reopened = CocStore(tmp / "coc.sqlite3")
    state = reopened.get_session_state(session_id)
    check("状态持久化（结局）", state.get("ended") == "burn", str(state))
    check("线索持久化（5 条）", len(reopened.discovered_clues(session_id)) == 5,
          str(len(reopened.discovered_clues(session_id))))
    check("事件里有 scene_enter", any(e["type"] == "scene_enter" for e in reopened.list_events(session_id, 50)))
    reopened.close()

    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    print(f"（临时库：{tmp / 'coc.sqlite3'}）")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
