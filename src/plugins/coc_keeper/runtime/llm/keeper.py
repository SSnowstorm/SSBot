"""NPC 台词生成：人设是约束，事实是边界，台词是输出。

- ``TemplateDialogueWriter``：按模组里预置的 ``answers``（关键词→台词）/ ``lines`` 选一句，
  零成本、离线可用，也是 LLM 失败时的兜底
- ``LlmDialogueWriter``：把「身份/态度/说话风格 + 本轮允许透露的事实」交给模型，
  让 NPC 说人话——但只准说被授权的事实
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Protocol

from nonebot.log import logger

from .client import LlmClient


@dataclass
class NpcLineRequest:
    name: str
    identity: str = ""
    attitude: str = ""
    voice: str = ""
    question: str = ""
    facts: list[str] = field(default_factory=list)
    reveal_text: str = ""
    answers: dict = field(default_factory=dict)
    lines: list[str] = field(default_factory=list)
    persona: str = ""

    def allowed_facts(self) -> list[str]:
        facts = [f for f in self.facts if f]
        if self.reveal_text:
            facts.append(self.reveal_text)
        return facts

    def public_brief(self) -> dict:
        """给模型看的公开信息（永远不含 secret）。"""
        return {
            "name": self.name,
            "identity": self.identity,
            "attitude": self.attitude,
            "voice": self.voice,
        }


class DialogueWriter(Protocol):
    async def write(self, request: NpcLineRequest, *, rng: random.Random | None = None) -> str | None: ...


class TemplateDialogueWriter:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    async def write(self, request: NpcLineRequest, *, rng: random.Random | None = None) -> str | None:
        rng = rng or self.rng
        question = request.question or ""
        base = ""
        for keyword, line in (request.answers or {}).items():
            if keyword and keyword in question:
                base = str(line)
                break
        if not base and request.lines:
            # 用问题文本做稳定散列选台词：不消耗 rng，保证骰点序列可复现
            seed = sum(ord(ch) for ch in (question or request.name))
            base = str(request.lines[seed % len(request.lines)])
        if not base:
            base = f"{request.name}看了你一眼，没有接话。"

        if request.reveal_text:
            return f"{base}\n{request.reveal_text}".strip()
        return base


SYSTEM = (
    "你在扮演克苏鲁跑团里的 NPC。只输出这个角色此刻说的一句话"
    "（可以带一个很短的语气/动作），不要旁白、不要解释规则、不要提骰子或数字。\n"
    "不要透露“你此刻可以说的事实”之外的任何信息；如果无话可说，就表现得不耐烦或沉默。"
)


class LlmDialogueWriter:
    def __init__(self, client: LlmClient, fallback: DialogueWriter | None = None):
        self.client = client
        self.fallback = fallback or TemplateDialogueWriter()

    async def write(self, request: NpcLineRequest, *, rng: random.Random | None = None) -> str | None:
        brief = request.public_brief()
        facts = request.allowed_facts()
        system = (
            SYSTEM
            + f"\n角色：{brief['name']}｜身份：{brief['identity'] or '未知'}｜"
            f"态度：{brief['attitude'] or '平常'}｜说话风格：{brief['voice'] or '自然'}"
        )
        if request.persona:
            system += f"\n整体语气参考：{request.persona}（只借语气，NPC 仍按自己的身份说话）"
        user = (
            f"玩家说：「{request.question or '……'}」\n"
            f"你此刻可以说的事实：{'；'.join(facts) if facts else '（你不想多说）'}\n"
            f"请用这个角色的口吻回一句（不超过 60 字）。"
        )
        text = await self.client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.9,
            max_tokens=160,
        )
        if not text:
            return await self.fallback.write(request, rng=rng)
        text = text.strip().strip('"“”')
        if len(text) > 220:
            text = text[:220].rstrip() + "…"
        if not text:
            return await self.fallback.write(request, rng=rng)
        return text
