"""人格接入测试：读取 suggarchat 人格、注入叙事与 NPC 台词。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_persona.py
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="coc_persona_"))
os.environ["APPDATA"] = str(TMP)

CFG_DIR = TMP / "nonebot2" / "onebot_plugin_suggarchat"
(CFG_DIR / "group_prompts").mkdir(parents=True, exist_ok=True)
(CFG_DIR / "private_prompts").mkdir(parents=True, exist_ok=True)
(CFG_DIR / "config.toml").write_text(
    'group_prompt_character = "Yuki"\nprivate_prompt_character = "Yuki"\n',
    encoding="utf-8",
)
PERSONA_TEXT = """你是 Yuki，一只小雪狐。

【性格基调】
- 亲和力拉满：语气柔和、有耐心，从不居高临下。
- 适度活泼：可以开玩笑，但不过度。
"""
(CFG_DIR / "group_prompts" / "Yuki.txt").write_text(PERSONA_TEXT, encoding="utf-8")
(CFG_DIR / "private_prompts" / "Yuki.txt").write_text(PERSONA_TEXT, encoding="utf-8")

import asyncio  # noqa: E402

from src.plugins.coc_keeper.domain import Investigator, hp_max, mp_max, san_max  # noqa: E402
from src.plugins.coc_keeper.module import load_module  # noqa: E402
from src.plugins.coc_keeper.runtime import CocRuntime, LlmNarrator, TemplateNarrator  # noqa: E402
from src.plugins.coc_keeper.runtime.llm import (  # noqa: E402
    IntentResult,
    LlmDialogueWriter,
    NpcLineRequest,
)
from src.plugins.coc_keeper.runtime.persona import (  # noqa: E402
    extract_brief,
    load_persona,
    persona_path,
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


class RecordingClient:
    def __init__(self, reply="叙事文本"):
        self.reply = reply
        self.available = True
        self.model = "fake"
        self.last_latency_ms = 5
        self.messages = None

    async def chat(self, messages, **kwargs):
        self.messages = messages
        return self.reply

    async def chat_json(self, *args, **kwargs):
        return None


class CaptureNarrator:
    def __init__(self):
        self.packets = []

    async def narrate(self, packet):
        self.packets.append(packet)
        return "叙述"


class FakeIntent:
    def __init__(self, kind):
        self.result = IntentResult(kind=kind, confidence=0.9, source="fake")

    async def parse(self, text, *, context):
        return self.result


def fixed_investigator() -> Investigator:
    attrs = {"STR": 30, "CON": 50, "SIZ": 30, "DEX": 60, "APP": 50, "INT": 60, "POW": 55, "EDU": 60}
    return Investigator(
        name="林医生", occupation="医生", attrs=attrs,
        state={"hp": hp_max(attrs), "mp": mp_max(attrs), "san": san_max(attrs), "luck": 50},
    )


async def main() -> None:
    print("== 人格读取 ==")
    persona = load_persona("group")
    check("读到配置里的人格", persona is not None and persona.name == "Yuki", str(persona))
    check("简介有内容", persona is not None and "小雪狐" in persona.brief, persona.brief[:60] if persona else "")
    check("简介被截断", persona is not None and len(persona.brief) <= 280, str(len(persona.brief) if persona else 0))
    check("路径指向 group_prompts", persona_path("group", "Yuki").parent.name == "group_prompts")
    check("off 模式不加载", load_persona("group", "off") is None)
    check("指定人格名可加载", (load_persona("group", "Yuki") or None) is not None)
    check("不存在的人格返回 None", load_persona("group", "Nobody") is None)
    check("简介去掉标题符号", "#" not in extract_brief(PERSONA_TEXT))

    print("\n== 注入叙事 prompt ==")
    client = RecordingClient()
    narrator = LlmNarrator(TemplateNarrator(), client)
    await narrator.narrate({
        "kind": "scene",
        "scene": {"player_text": "码头被雾吞掉一半。"},
        "persona": {"name": "Yuki", "brief": "小雪狐：语气柔和，偶尔活泼"},
        "forbidden": [],
    })
    system = client.messages[0]["content"]
    check("system 含人格名", "Yuki" in system, system[:100])
    check("system 含人格简介", "语气柔和" in system, system[:160])
    check("system 明确只借语气", "只借语气" in system, system[:200])

    print("\n== 注入 NPC 台词 prompt ==")
    client2 = RecordingClient("我什么都不知道。")
    writer = LlmDialogueWriter(client2)
    request = NpcLineRequest(
        name="老陈", identity="码头看守", attitude="警惕", voice="短句",
        question="你知道信的事吗", persona="小雪狐：语气柔和",
    )
    line = await writer.write(request)
    system2 = client2.messages[0]["content"]
    check("台词 system 含语气参考", "整体语气参考" in system2 and "小雪狐" in system2, system2[:160])
    check("台词仍按 NPC 身份", "码头看守" in system2)
    check("返回台词", line == "我什么都不知道。", repr(line))

    print("\n== 引擎把人格放进事实包 ==")
    module = load_module(MODULE_PATH)
    store = CocStore(TMP / "coc.sqlite3")
    module_id = store.save_module(module)
    campaign_id = store.create_campaign(module.title, group_id=527020285)
    store.set_campaign_module(campaign_id, module_id)
    store.save_character(campaign_id, fixed_investigator(), owner_qq=10001)
    capture = CaptureNarrator()
    runtime = CocRuntime(
        store, capture, intent_parser=FakeIntent("env"),
        persona_loader=lambda scene: load_persona(scene, "Yuki"),
    )
    await runtime.start(campaign_id, module_id)
    packet = capture.packets[-1]
    check("事实包含 persona", bool(packet.get("persona")), str(packet.get("persona")))
    check("persona 名与简介齐全",
          packet["persona"].get("name") == "Yuki" and bool(packet["persona"].get("brief")),
          str(packet.get("persona")))

    print("\n== 关闭人格 ==")
    runtime2 = CocRuntime(
        store, CaptureNarrator(), intent_parser=FakeIntent("env"),
        persona_loader=lambda scene: load_persona(scene, "off"),
    )
    campaign2 = store.create_campaign(module.title, group_id=888888)
    store.set_campaign_module(campaign2, module_id)
    store.save_character(campaign2, fixed_investigator(), owner_qq=10001)
    await runtime2.start(campaign2, module_id)
    packet2 = runtime2.narrator.packets[-1]
    check("off 时事实包无 persona", "persona" not in packet2, str(packet2.keys()))

    store.close()
    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
