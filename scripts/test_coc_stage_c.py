"""C 阶段测试：免命令分类、风格档位、LLM 调用审计。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_stage_c.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os  # noqa: E402
import tempfile as _tempfile  # noqa: E402

os.environ["COC_DB_PATH"] = str(Path(_tempfile.mkdtemp(prefix="coc_c_stage_")) / "coc.sqlite3")

import nonebot  # noqa: E402

nonebot.init(driver="~fastapi", host="127.0.0.1", port=18997, superusers={"1"})
nonebot.load_plugin("src.plugins.coc_keeper")

from src.plugins.coc_keeper.domain import Investigator, hp_max, mp_max, san_max  # noqa: E402
from src.plugins.coc_keeper.module import load_module  # noqa: E402
from src.plugins.coc_keeper.replay import build_replay  # noqa: E402
from src.plugins.coc_keeper.runtime import CocRuntime, LlmNarrator, TemplateNarrator  # noqa: E402
from src.plugins.coc_keeper.runtime.llm import IntentResult  # noqa: E402
from src.plugins.coc_keeper.runtime.style import get_style  # noqa: E402
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


class FakeIntent:
    def __init__(self, kind):
        self.result = IntentResult(kind=kind, confidence=0.9, source="fake")

    async def parse(self, text, *, context):
        return self.result


class MetaNarrator:
    """返回固定文本，并暴露 last_meta 供审计。"""

    def __init__(self, text="叙述", meta=None):
        self.text = text
        self.last_meta = meta or {
            "kind": "scene", "model": "fake", "latency_ms": 120,
            "retried": False, "fallback": False, "passthrough": False,
        }

    async def narrate(self, packet):
        self.last_meta = dict(self.last_meta, kind=packet.get("kind"))
        return self.text


class RecordingClient:
    def __init__(self, reply="叙事文本"):
        self.reply = reply
        self.available = True
        self.model = "fake"
        self.last_latency_ms = 10
        self.messages = None

    async def chat(self, messages, **kwargs):
        self.messages = messages
        return self.reply

    async def chat_json(self, *args, **kwargs):
        return None


def fixed_investigator() -> Investigator:
    attrs = {"STR": 30, "CON": 50, "SIZ": 30, "DEX": 60, "APP": 50, "INT": 60, "POW": 55, "EDU": 60}
    return Investigator(
        name="林医生", occupation="医生", attrs=attrs, skills={"侦查": 65},
        state={"hp": hp_max(attrs), "mp": mp_max(attrs), "san": san_max(attrs), "luck": 50},
    )


async def main() -> None:
    print("== 免命令分类 ==")
    from src.plugins.coc_keeper._commands import classify_ambient  # 延迟导入，需要 nonebot 初始化

    cases = [
        ("/coc 行动 看看", "command"),
        ("!help", "command"),
        ("ooc: 这个规则怎么算", "ooc"),
        ("（我看看四周）", "ooc"),
        ("// 问一下", "ooc"),
        ("我检查那封信", "action"),
        ("", "ignore"),
        ("。", "ignore"),
    ]
    for text, expected in cases:
        kind, _ = classify_ambient(text)
        check(f"{text!r} → {expected}", kind == expected, f"got {kind}")
    kind, body = classify_ambient("（我看看四周）")
    check("OOC 去掉包裹符", body == "我看看四周", repr(body))

    print("\n== 风格档位 ==")
    check("宽松档提示更早", get_style("lenient").hint_at == 2, str(get_style("lenient").hint_at))
    check("残酷档提示更晚", get_style("cruel").hint_at == 4, str(get_style("cruel").hint_at))
    check("未知档位回退标准", get_style("whatever").key == "standard")
    check("档位影响叙事指令", get_style("cruel").narration != get_style("lenient").narration)

    print("\n== 风格影响卡关阈值 ==")
    module = load_module(MODULE_PATH)
    tmp = Path(tempfile.mkdtemp(prefix="coc_stage_c_"))
    store = CocStore(tmp / "coc.sqlite3")
    module_id = store.save_module(module)

    async def run_campaign(style: str, acts: int) -> str:
        campaign_id = store.create_campaign(module.title, group_id=hash(style) % 100000, keeper_style=style)
        store.set_campaign_module(campaign_id, module_id)
        store.save_character(campaign_id, fixed_investigator(), owner_qq=10001)
        runtime = CocRuntime(store, TemplateNarrator(), intent_parser=FakeIntent("env"))
        await runtime.start(campaign_id, module_id)
        session_id = int(store.find_running_session(campaign_id)["id"])
        narrative = ""
        for _ in range(acts):
            narrative = (await runtime.act(session_id, 10001, "看看周围")).narrative
        return narrative

    lenient_text = await run_campaign("lenient", 2)
    check("宽松档 2 轮就提示", "KP 提示" in lenient_text, lenient_text[-60:])
    cruel_early = await run_campaign("cruel", 2)
    check("残酷档 2 轮不提示", "KP 提示" not in cruel_early, cruel_early[-60:])
    cruel_text = await run_campaign("cruel", 4)
    check("残酷档 4 轮才提示", "KP 备注" in cruel_text, cruel_text[-60:])

    print("\n== 风格进入叙事 prompt ==")
    client = RecordingClient()
    narrator = LlmNarrator(TemplateNarrator(), client)
    await narrator.narrate({
        "kind": "scene",
        "scene": {"player_text": "码头被雾吞掉一半。"},
        "style": {"narration": "叙事冷硬，失败就是失败。"},
        "forbidden": [],
    })
    system = client.messages[0]["content"]
    check("system 含风格指令", "叙事冷硬" in system, system[:120])

    print("\n== LLM 调用审计 ==")
    campaign_id = store.create_campaign(module.title, group_id=777777)
    store.set_campaign_module(campaign_id, module_id)
    store.save_character(campaign_id, fixed_investigator(), owner_qq=10001)
    meta_narrator = MetaNarrator()
    runtime = CocRuntime(store, meta_narrator, intent_parser=FakeIntent("env"))
    await runtime.start(campaign_id, module_id)
    session_id = int(store.find_running_session(campaign_id)["id"])
    await runtime.act(session_id, 10001, "看看周围")

    events = store.list_events(session_id, 100)
    llm_events = [e for e in events if e["type"] == "llm_call"]
    check("记录 llm_call 事件", len(llm_events) >= 2, str(len(llm_events)))
    check("事件含模型与耗时", llm_events[0]["payload"].get("model") == "fake"
          and llm_events[0]["payload"].get("latency_ms") == 120, str(llm_events[0]["payload"]))

    report = build_replay(store, session_id)
    check("复盘统计 LLM 次数", report.stats.get("llm_calls", 0) >= 2, str(report.stats.get("llm_calls")))
    check("复盘样式含 LLM 行", "LLM 叙事调用" in report.markdown, report.markdown[:200])

    store.close()
    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    print(f"（临时目录：{tmp}）")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
