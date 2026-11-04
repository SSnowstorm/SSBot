"""A 阶段测试：意图解析（LLM + 规则兜底）、场景细节、NPC 台词与守卫。

不联网：用 FakeClient / FakeIntent / FakeDialogue 注入。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_intent.py
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
from src.plugins.coc_keeper.runtime.llm import (  # noqa: E402
    IntentResult,
    LlmIntentParser,
    RuleIntentParser,
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


class FakeClient:
    def __init__(self, payload=None):
        self.payload = payload
        self.calls = 0

    async def chat_json(self, *args, **kwargs):
        self.calls += 1
        return self.payload

    async def chat(self, *args, **kwargs):
        self.calls += 1
        return None


class FakeIntent:
    def __init__(self, kind, target="", confidence=0.9, clarify=""):
        self.result = IntentResult(kind=kind, target=target, confidence=confidence, clarify=clarify, source="fake")

    async def parse(self, text, *, context):
        return self.result


class FakeDialogue:
    def __init__(self, text):
        self.text = text
        self.requests = []

    async def write(self, request, *, rng=None):
        self.requests.append(request)
        return self.text


def fixed_investigator() -> Investigator:
    attrs = {"STR": 30, "CON": 50, "SIZ": 30, "DEX": 60, "APP": 50, "INT": 60, "POW": 55, "EDU": 60}
    return Investigator(
        name="林医生", occupation="医生", attrs=attrs,
        skills={"斗殴": 60, "闪避": 40, "侦查": 65},
        state={"hp": hp_max(attrs), "mp": mp_max(attrs), "san": san_max(attrs), "luck": 50},
    )


async def main() -> None:
    module = load_module(MODULE_PATH)
    tmp = Path(tempfile.mkdtemp(prefix="coc_intent_"))
    store = CocStore(tmp / "coc.sqlite3")
    module_id = store.save_module(module)
    campaign_id = store.create_campaign(module.title, group_id=527020285)
    store.set_campaign_module(campaign_id, module_id)
    store.save_character(campaign_id, fixed_investigator(), owner_qq=10001)

    runtime = CocRuntime(store, TemplateNarrator())
    await runtime.start(campaign_id, module_id)
    session_id = int(store.find_running_session(campaign_id)["id"])

    print("== 模块新字段 ==")
    check("场景有细节池", all(len(s.details) >= 3 for s in module.scenes.values()),
          str([len(s.details) for s in module.scenes.values()]))
    check("线索有别名", module.clue("letter").aliases == ["信", "信纸", "那封信", "湿透的信"])
    check("NPC 有台词库", bool(module.npc("dockhand").lines))

    print("\n== 候选集 ==")
    scene = module.scene("harbor")
    candidates = runtime._build_candidates(module, scene, session_id)
    ids = {c["id"] for c in candidates}
    check("含线索/NPC/出口", {"letter", "dock_tip", "dockhand"}.issubset(ids), str(sorted(ids)))
    check("未发现线索标 undiscovered", any(c["id"] == "letter" and c["state"] == "undiscovered" for c in candidates))
    check("出口默认 locked（需要信）", any(c["type"] == "exit" and c["state"] == "locked" for c in candidates))
    check("候选带别名", any(c["id"] == "letter" and "那封信" in c["aliases"] for c in candidates))

    print("\n== 意图解析 ==")
    rule = await RuleIntentParser().parse("我查看湿透的信", context={"candidates": candidates})
    check("规则解析：调查", rule.kind == "investigate", str(rule))

    client = FakeClient({"kind": "talk", "target_id": "dockhand", "confidence": 0.9, "approach": "压低声音"})
    parser = LlmIntentParser(client, RuleIntentParser())
    intent = await parser.parse("我想跟那个看码头的老头唠两句", context={"candidates": candidates, "scene": "雾港码头"})
    check("LLM 解析：target_id 映射成中文名", intent.target == "老陈" and intent.kind == "talk", str(intent))
    check("LLM 解析：source=llm", intent.source == "llm")

    broken = LlmIntentParser(FakeClient(None), RuleIntentParser())
    fallback = await broken.parse("我查看湿透的信", context={"candidates": candidates})
    check("LLM 失败回退规则", fallback.source == "rule" and fallback.kind == "investigate", str(fallback))

    print("\n== 场景细节（env） ==")
    env_runtime = CocRuntime(store, TemplateNarrator(), intent_parser=FakeIntent("env"))
    first = await env_runtime.act(session_id, 10001, "确认一下周围哪里有灯")
    check("env 返回第一条细节", first.kind == "env" and scene.details[0] in first.narrative, first.narrative[:60])
    second = await env_runtime.act(session_id, 10001, "再听听有什么动静")
    check("第二条不重复", second.narrative.strip() == scene.details[1], second.narrative[:60])
    for _ in range(2):
        await env_runtime.act(session_id, 10001, "继续观察")
    exhausted = await env_runtime.act(session_id, 10001, "再看看")
    check("细节用完给出提示", "看得很仔细" in exhausted.narrative, exhausted.narrative[:60])

    print("\n== NPC 台词 ==")
    dialogue = FakeDialogue("【测试台词】后半夜的事，我什么都没看见。")
    talk_runtime = CocRuntime(store, TemplateNarrator(), intent_parser=FakeIntent("talk", "老陈"), dialogue=dialogue)
    talk = await talk_runtime.act(session_id, 10001, "我想跟那个看码头的老头唠两句")
    check("台词来自 writer", "测试台词" in talk.narrative, talk.narrative[:80])
    check("不再输出 attitude", "警惕但怕事" not in talk.narrative)
    check("不再输出 voice", "短句，带方言" not in talk.narrative)
    check("首次搭话触发线索", store.has_clue(session_id, "dock_tip"))
    request = dialogue.requests[0]
    check("request 带人设", request.identity == "码头看守" and request.voice.startswith("短句"))
    check("首次允许透露", bool(request.reveal_text))

    print("\n== 线索守卫 ==")
    guard_dialogue = FakeDialogue("【老陈】昨儿后半夜，局长带人往仓库搬箱子")
    guard_runtime = CocRuntime(store, TemplateNarrator(), intent_parser=FakeIntent("talk", "老陈"), dialogue=guard_dialogue)
    guarded = await guard_runtime.act(session_id, 10001, "再问一遍")
    check("已发现后不再重复透露", not guard_dialogue.requests[-1].reveal_text)
    check("台词里不再出现线索原文", "局长带人往仓库搬箱子" not in guarded.narrative, guarded.narrative[:80])

    print("\n== 低置信度反问 ==")
    clarify_runtime = CocRuntime(store, TemplateNarrator(), intent_parser=FakeIntent("investigate", "湿透的信", 0.2))
    clarified = await clarify_runtime.act(session_id, 10001, "嗯……那个")
    check("低置信度不猜", "你想做什么" in clarified.narrative, clarified.narrative[:80])
    check("反问给具体选项", "湿透的信" in clarified.narrative or "老陈" in clarified.narrative, clarified.narrative[:80])

    print("\n== 事件留痕 ==")
    events = store.list_events(session_id, 200)
    check("记录 intent 事件", any(e["type"] == "intent" for e in events))
    check("记录 env 行动", any(e["type"] == "action" for e in events))

    store.close()
    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    print(f"（临时目录：{tmp}）")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
