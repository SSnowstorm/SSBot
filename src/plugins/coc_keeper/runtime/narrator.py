"""叙事适配层：把「事实包」变成 2-4 句中文。

两种实现：
- ``TemplateNarrator``：确定性模板，离线可用，测试默认用它
- ``LlmNarrator``：模型写叙事；输出先过守卫（剧透/规则/长度），不过就重写一次，
  再不过回退模板——跑团流程永不被模型卡住

事实包只包含「玩家可见」信息。``forbidden`` 字段只在守卫里用，不发给模型。
"""

from __future__ import annotations

import json
import os
from typing import Protocol, runtime_checkable

from nonebot.log import logger

from .llm.client import LlmClient
from .llm.guard import check as guard_check


@runtime_checkable
class Narrator(Protocol):
    async def narrate(self, packet: dict) -> str: ...


class TemplateNarrator:
    """确定性叙事：不联网、可复现，作为兜底与测试基线。"""

    async def narrate(self, packet: dict) -> str:
        kind = packet.get("kind")
        if kind == "scene":
            scene = packet.get("scene") or {}
            choices = packet.get("choices") or []
            text = scene.get("player_text") or ""
            tail = ("\n可行动：" + "；".join(choices)) if choices else ""
            return (text + tail).strip()
        if kind == "clue":
            clue = packet.get("clue") or {}
            return clue.get("player_text") or "你发现了点什么，但说不清是什么。"
        if kind == "check_fail":
            check = packet.get("check") or {}
            return f"你的{check.get('skill', '尝试')}没有成功（{check.get('roll')}/{check.get('target')}），眼前的东西依旧模糊。"
        if kind == "blocked":
            return packet.get("text") or "那里过不去。"
        if kind == "npc":
            npc = packet.get("npc") or {}
            return npc.get("line") or f"{npc.get('name', '对方')}没有回答。"
        if kind == "ending":
            return packet.get("text") or "故事在这里结束了。"
        if kind == "clarify":
            return packet.get("text") or "你是想做什么？可以说得具体一点。"
        if kind == "env":
            return packet.get("text") or "你看了看四周，没什么特别的。"
        if kind in ("combat", "sanity"):
            return packet.get("text") or "……"
        if kind == "wait":
            return packet.get("text") or "你们在原地等了一会儿，雾更浓了。"
        return packet.get("text") or "……"


class LlmNarrator:
    """模型叙事 + 守卫 + 模板兜底。"""

    # 这些 kind 的事实文本已经由别的组件写好，不再二次生成
    _PASSTHROUGH = {"npc", "combat", "sanity", "env"}

    def __init__(self, fallback: Narrator | None = None, client: LlmClient | None = None):
        self.fallback = fallback or TemplateNarrator()
        self.client = client or LlmClient()
        self.model = self.client.model

    @property
    def available(self) -> bool:
        return self.client.available

    @staticmethod
    def _instructions(kind: str) -> str:
        return {
            "scene": "用 2-3 句描写玩家刚看到的场景，氛围偏阴冷，不要替玩家做决定。",
            "clue": "用 1-2 句描述玩家发现线索的瞬间，自然带出线索内容。",
            "check_fail": "用 1-2 句描写失败的结果：给出新的感官细节或方向，不要复述骰点，不要说“你失败了”。",
            "ending": "用 2-3 句收束这一局，语气克制。",
            "clarify": "用一句话请玩家说清楚要做什么，不要猜。",
            "blocked": "用一句话说明这里过不去，不要透露隐藏条件。",
            "wait": "用一句话描写等待时环境的变化。",
        }.get(kind, "用 1-2 句推进剧情。")

    async def _generate(self, packet: dict, *, strict: bool) -> str | None:
        kind = str(packet.get("kind") or "")
        recent = packet.get("recent") or []
        summary = packet.get("summary") or ""
        discovered = packet.get("discovered") or []
        body = {k: v for k, v in packet.items() if k not in ("forbidden", "recent", "summary")}

        system = (
            "你是克苏鲁的呼唤（CoC 7e）跑团的守秘人。"
            "只输出叙事正文，不要输出规则、骰点、内心独白或元叙述；不要替玩家做决定。"
            + self._instructions(kind)
        )
        if strict:
            system += "重写要求：不要提到任何尚未发现的线索内容，不要写数字、骰点、检定或成功率。"

        parts = [f"事实包：{json.dumps(body, ensure_ascii=False)}"]
        if summary:
            parts.append(f"此前摘要：{summary}")
        if recent:
            parts.append("最近的对话：\n" + "\n".join(
                ("玩家：" if item.get("role") == "player" else "守秘人：") + str(item.get("text") or "")
                for item in recent[-4:]
            ))
        if discovered:
            parts.append("已发现线索：" + "、".join(str(x) for x in discovered[:8]))

        return await self.client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(parts)}],
            temperature=0.8,
            max_tokens=320,
        )

    async def narrate(self, packet: dict) -> str:
        kind = str(packet.get("kind") or "")
        if kind in self._PASSTHROUGH or not self.available:
            return await self.fallback.narrate(packet)

        secrets = list(packet.get("forbidden") or [])
        text = await self._generate(packet, strict=False)
        if text and guard_check(text, secrets=secrets).ok:
            return text.strip()

        retry = await self._generate(packet, strict=True)
        if retry and guard_check(retry, secrets=secrets).ok:
            return retry.strip()

        sample = text or retry or ""
        if sample:
            reasons = guard_check(sample, secrets=secrets).reasons
            logger.info(f"[coc] 叙事未通过守卫（{reasons}），回退模板")
        return await self.fallback.narrate(packet)


def build_narrator() -> Narrator:
    """按环境变量选择叙事实现（默认模板，显式开启才调 LLM）。"""
    enabled = os.getenv("COC_LLM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if enabled:
        narrator = LlmNarrator()
        logger.info(f"[coc] 叙事: LLM({narrator.model}) 可用={narrator.available}，失败回退模板")
        return narrator
    return TemplateNarrator()
