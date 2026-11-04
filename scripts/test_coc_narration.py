"""B 阶段测试：叙事守卫、LLM 叙事的重写/回退、连续性记忆与事实包注入。

不联网：FakeClient / CaptureNarrator 注入。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_narration.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.plugins.coc_keeper.domain import Investigator, hp_max, mp_max, san_max  # noqa: E402
from src.plugins.coc_keeper.module import load_module  # noqa: E402
from src.plugins.coc_keeper.runtime import CocRuntime, LlmNarrator, TemplateNarrator  # noqa: E402
from src.plugins.coc_keeper.runtime.llm import (  # noqa: E402
    IntentResult,
    append_turn,
    guard_check,
    maybe_summarize,
)
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


class SeqClient:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0
        self.available = True
        self.model = "fake"

    async def chat(self, messages, **kwargs):
        self.calls += 1
        return self.texts.pop(0) if self.texts else None

    async def chat_json(self, *args, **kwargs):
        return None


class CaptureNarrator:
    def __init__(self, text="叙述"):
        self.text = text
        self.packets = []

    async def narrate(self, packet):
        self.packets.append(packet)
        return self.text


class FakeIntent:
    def __init__(self, kind, target=""):
        self.result = IntentResult(kind=kind, target=target, confidence=0.9, source="fake")

    async def parse(self, text, *, context):
        return self.result


def fixed_investigator() -> Investigator:
    attrs = {"STR": 30, "CON": 50, "SIZ": 30, "DEX": 60, "APP": 50, "INT": 60, "POW": 55, "EDU": 60}
    return Investigator(
        name="林医生", occupation="医生", attrs=attrs,
        skills={"侦查": 65}, state={"hp": hp_max(attrs), "mp": mp_max(attrs), "san": san_max(attrs), "luck": 50},
    )


async def main() -> None:
    module = load_module(MODULE_PATH)
    secret = module.clue("ritual").player_text
    keeper = module.scene("warehouse").keeper_text

    print("== 叙事守卫 ==")
    check("正常叙事通过", guard_check("雾更浓了，你听见远处有铁链拖动的声音。").ok)
    check("剧透被拦", not guard_check(f"你看到{secret}", secrets=[secret]).ok)
    check("骰点被拦", not guard_check("你的侦查检定 77/25 失败").ok)
    check("keeper 文本被拦", not guard_check(f"（真相）{keeper}", secrets=[keeper]).ok)
    check("超长被拦", not guard_check("字" * 700).ok)

    print("\n== LLM 叙事：重写与回退 ==")
    leaky = "你的侦查检定成功了，77/25。"          # 规则泄漏
    clean = "灯罩上的盐霜被雾打湿，你凑近才看清信纸边缘的压痕。"
    client = SeqClient([leaky, clean])
    narrator = LlmNarrator(TemplateNarrator(), client)
    text = await narrator.narrate({"kind": "clue", "clue": {"player_text": "x"}, "forbidden": []})
    check("第一次不合格 → 重写后采用", text == clean and client.calls == 2, f"{text!r} calls={client.calls}")

    client2 = SeqClient(["77/25 检定成功", "还是 77/25"])
    narrator2 = LlmNarrator(TemplateNarrator(), client2)
    packet = {"kind": "scene", "scene": {"player_text": "码头被雾吞掉一半。"}, "forbidden": []}
    text2 = await narrator2.narrate(packet)
    check("两次都不合格 → 回退模板", text2 == "码头被雾吞掉一半。", text2[:40])

    client3 = SeqClient([secret])
    narrator3 = LlmNarrator(TemplateNarrator(), client3)
    text3 = await narrator3.narrate({"kind": "clue", "clue": {"player_text": "x"}, "forbidden": [secret]})
    check("剧透 → 不回退到模型文本", secret not in text3, text3[:40])

    print("\n== 透传类型 ==")
    client4 = SeqClient(["不该被调用"])
    narrator4 = LlmNarrator(TemplateNarrator(), client4)
    npc_text = await narrator4.narrate({"kind": "npc", "npc": {"name": "老陈", "line": "我什么都没看见。"}})
    check("npc 不再二次生成", npc_text == "我什么都没看见。" and client4.calls == 0, f"{npc_text!r} calls={client4.calls}")

    print("\n== 连续性记忆 ==")
    state = {}
    for i in range(10):
        append_turn(state, f"玩家第{i}句", f"守秘人第{i}句")
    check("recent 有上限", len(state["recent"]) == 16, str(len(state["recent"])))
    check("只保留最近", state["recent"][-1]["text"] == "守秘人第9句")

    summary_client = SeqClient(["他们在码头查信，老陈不肯多说。"])
    updated = await maybe_summarize(summary_client, state, 10)
    check("第 10 回合触发摘要", updated and state["summary"].startswith("他们在码头"), state.get("summary"))
    not_updated = await maybe_summarize(summary_client, state, 11)
    check("非整 10 回合不触发", not not_updated)

    print("\n== 事实包注入 ==")
    tmp = Path(tempfile.mkdtemp(prefix="coc_narr_"))
    store = CocStore(tmp / "coc.sqlite3")
    module_id = store.save_module(module)
    campaign_id = store.create_campaign(module.title, group_id=1)
    store.set_campaign_module(campaign_id, module_id)
    store.save_character(campaign_id, fixed_investigator(), owner_qq=10001)

    capture = CaptureNarrator("雾里的灯晃了一下。")
    runtime = CocRuntime(store, capture, intent_parser=FakeIntent("env"))
    await runtime.start(campaign_id, module_id)
    session_id = int(store.find_running_session(campaign_id)["id"])
    start_packet = capture.packets[-1]
    check("场景包带 forbidden", bool(start_packet.get("forbidden")), str(len(start_packet.get("forbidden") or [])))
    check("forbidden 含 keeper 文本", keeper in start_packet["forbidden"])
    check("forbidden 不含已公开场景文本", module.scene("harbor").player_text not in start_packet["forbidden"])

    await runtime.act(session_id, 10001, "看看周围")
    state_after = store.get_session_state(session_id)
    check("回合写入 recent", len(state_after.get("recent") or []) == 2, str(state_after.get("recent")))
    first_packet = capture.packets[-1]
    check("首回合没有历史可注入", len(first_packet.get("recent") or []) == 0, str(len(first_packet.get("recent") or [])))

    await runtime.act(session_id, 10001, "再听听动静")
    second_packet = capture.packets[-1]
    check("第二回合带上最近对话", len(second_packet.get("recent") or []) == 2,
          str(len(second_packet.get("recent") or [])))
    check("叙事包保留 forbidden 字段", "forbidden" in second_packet)

    store.close()
    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    print(f"（临时目录：{tmp}）")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
