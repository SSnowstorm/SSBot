"""P2 复盘 + 卡关兜底测试。

跑一局（模板叙事、固定骰子）→ 触发软提示 → 生成战报 → 校验内容与统计。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_replay.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.plugins.coc_keeper.domain import random_investigator  # noqa: E402
from src.plugins.coc_keeper.module import load_module  # noqa: E402
from src.plugins.coc_keeper.replay import build_replay, save_replay  # noqa: E402
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


async def main() -> None:
    module = load_module(MODULE_PATH)
    tmp = Path(tempfile.mkdtemp(prefix="coc_replay_"))
    store = CocStore(tmp / "coc.sqlite3")
    module_id = store.save_module(module)
    campaign_id = store.create_campaign(module.title, group_id=527020285)
    store.set_campaign_module(campaign_id, module_id)
    store.save_character(campaign_id, random_investigator(name="林医生"), owner_qq=10001)

    runtime = CocRuntime(store, TemplateNarrator(), SeqRng([5, 0]))
    await runtime.start(campaign_id, module_id)
    session = store.find_running_session(campaign_id)
    session_id = int(session["id"])

    await runtime.act(session_id, 10001, "我检查那封信")
    await runtime.act(session_id, 10001, "我和老陈说话")
    await runtime.act(session_id, 10001, "我去废弃仓库")

    print("== 卡关兜底 ==")
    results = []
    for _ in range(3):
        results.append(await runtime.act(session_id, 10001, "随便看看"))
    hinted = results[-1].narrative
    check("连续 3 轮无进展 → 出现 KP 提示", "（KP 提示）" in hinted, hinted[:80])
    check("提示指向未发现线索或出口", any(k in hinted for k in ("木箱", "账本", "符号", "回码头", "去灯塔")), hinted[:80])
    events = store.list_events(session_id, 100)
    check("记了 keeper_mercy 事件",
          any(e["type"] == "keeper_mercy" for e in events), str([e["type"] for e in events]))
    check("提示只出现一次", sum(1 for r in results if "（KP 提示）" in r.narrative) == 1,
          str([r.narrative[-40:] for r in results]))

    print("\n== 生成战报 ==")
    report = build_replay(store, session_id)
    md = report.markdown
    check("标题含模组名", "雾港的来信" in md)
    check("含时间线章节", "## 时间线" in md)
    check("含骰点章节", "## 骰点" in md)
    check("含已发现线索章节", "## 已发现线索" in md)
    check("时间线记录了场景", "雾港码头" in md)
    check("时间线记录了线索", "湿透的信" in md)
    check("骰点表记录了技能", "侦查" in md and "d100" not in md.split("## 骰点")[0])
    check("统计：线索 2/5", report.stats["clues_found"] == 2 and report.stats["clues_total"] == 5,
          str(report.stats))
    check("统计：至少 1 次掷骰", report.stats["rolls"] >= 1, str(report.stats))
    check("统计：成功率在 0-100", 0 <= report.stats["success_rate"] <= 100, str(report.stats))

    path = save_replay(report, tmp / "replays")
    check("战报文件已写入", path.is_file() and path.stat().st_size > 200, str(path))
    check("文件内容与报告一致", "雾港的来信" in path.read_text(encoding="utf-8"))

    print("\n== 结束后复盘 ==")
    state = store.get_session_state(session_id)
    state["ended"] = "manual"
    store.update_session_state(session_id, state)
    store.end_session(session_id)
    store.append_event(session_id, "session_end", actor="10001", payload={"ending": "manual"})
    final = build_replay(store, session_id)
    check("结束状态进入统计", final.stats["ending"] == "manual", str(final.stats))
    check("时间线含结束条目", "本局结束" in final.markdown)

    store.close()
    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    print(f"（临时目录：{tmp}）")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
