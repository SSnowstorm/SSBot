"""叙事适配层：把「事实包」变成 2-4 句中文。

两种实现：
- ``TemplateNarrator``：确定性模板，离线可用，测试默认用它
- ``LlmNarrator``：调 DeepSeek 写氛围叙事；失败自动回退模板（不影响跑团流程）

事实包（packet）只包含「玩家可见」信息：场景 public 文本、已发现线索、NPC 公开面。
``keeper_text`` / 未发现线索永远不会进 packet —— 这是数据层约束（设计文档 5.4）。
"""

from __future__ import annotations

import json
import os
from typing import Protocol, runtime_checkable

import httpx
from nonebot.log import logger


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
        if kind in ("combat", "sanity"):
            return packet.get("text") or "……"
        if kind == "wait":
            return packet.get("text") or "你们在原地等了一会儿，雾更浓了。"
        return packet.get("text") or "……"


class LlmNarrator:
    """调 DeepSeek 写叙事；任何异常都回退模板，保证跑团不中断。"""

    def __init__(self, fallback: Narrator | None = None):
        self.fallback = fallback or TemplateNarrator()
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.base_url = os.getenv("COC_LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
        self.model = os.getenv("COC_LLM_MODEL", "deepseek-chat")
        self.timeout = float(os.getenv("COC_LLM_TIMEOUT", "25"))

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def narrate(self, packet: dict) -> str:
        if not self.available:
            return await self.fallback.narrate(packet)

        kind = packet.get("kind")
        instructions = {
            "scene": "用 2-3 句描写玩家刚看到的场景，氛围偏阴冷，不要替玩家做决定。",
            "clue": "用 1-2 句描述玩家发现线索的瞬间，结尾自然带出线索内容。",
            "check_fail": "用 1-2 句描写失败的结果，不要复述骰点，不要给额外线索。",
            "npc": "只写这个 NPC 的一句台词，不要旁白，不要解释规则。",
            "ending": "用 2-3 句收束这一局，语气克制。",
            "clarify": "用一句话请玩家说清楚要做什么，不要猜。",
            "blocked": "用一句话说明这里过不去，不要透露隐藏条件。",
            "wait": "用一句话描写等待时环境的变化。",
            "combat": "用 1-2 句描写这一轮交锋的结果，不要复述骰点。",
            "sanity": "用 1-2 句描写理智受创的感受，不要解释规则。",
        }.get(kind, "用 1-2 句推进剧情。")

        messages = [
            {
                "role": "system",
                "content": (
                    "你是克苏鲁的呼唤（CoC 7e）跑团的守秘人。"
                    "只输出叙事正文，不要输出规则、骰点、内心独白或元叙述。"
                    + instructions
                ),
            },
            {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
        ]
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.8,
                        "max_tokens": 220,
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            text = (data["choices"][0]["message"]["content"] or "").strip()
            return text or await self.fallback.narrate(packet)
        except Exception as exc:  # 网络/额度/格式问题一律回退
            logger.warning(f"[coc] LLM 叙事失败，回退模板: {exc!r}")
            return await self.fallback.narrate(packet)


def build_narrator() -> Narrator:
    """按环境变量选择叙事实现（默认模板，显式开启才调 LLM）。"""
    enabled = os.getenv("COC_LLM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if enabled:
        narrator = LlmNarrator()
        logger.info(f"[coc] 叙事: LLM({narrator.model}) 可用={narrator.available}，失败回退模板")
        return narrator
    return TemplateNarrator()
