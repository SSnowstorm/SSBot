"""意图解析：把玩家原话变成结构化 intent。

两种实现：
- ``RuleIntentParser``：复用现有 ``parse_action``，零成本、离线可用，作为兜底
- ``LlmIntentParser``：让模型在「候选实体清单」里选，解决换说法听不懂

关键约束：模型只能从候选集里选（``target_id`` 必须命中或为 ``unmatched``），
不允许它凭空创造对象；置信度不足时交回调用方反问。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from nonebot.log import logger

from ..actions import parse_action
from .client import LlmClient

KINDS = {
    "investigate", "talk", "move", "use", "attack", "dodge",
    "wait", "env", "unclear", "custom",
}

# 低于这个置信度就反问，不猜
MIN_CONFIDENCE = 0.5


@dataclass
class IntentResult:
    kind: str
    target: str = ""
    approach: str = ""
    confidence: float = 1.0
    clarify: str = ""
    source: str = "rule"
    raw: dict = field(default_factory=dict)


class IntentParser(Protocol):
    async def parse(self, text: str, *, context: dict) -> IntentResult: ...


def _candidate_lines(candidates: list[dict]) -> str:
    lines = []
    for item in candidates:
        aliases = "/".join(item.get("aliases") or []) or "-"
        state = item.get("state") or ""
        lines.append(f"  {item['id']} | {item['name']} | {aliases} | {state}")
    return "\n".join(lines) if lines else "  （无）"


SYSTEM = (
    "你是跑团主持人（KP）的意图解析器。只输出 JSON，不要解释、不要 Markdown。\n"
    "把玩家的话解析成一个动作。target_id 只能从候选清单里选；"
    "如果都不是，返回 target_id=\"unmatched\"。\n"
    "kind 只能是：investigate（调查/查看/搜查）、talk（询问/搭话）、move（去某处）、"
    "use（使用/操作物品）、attack（攻击）、dodge（躲闪）、wait（等待）、"
    "env（观察环境/听声音/感受气氛，没有具体对象）、unclear（实在无法判断）。\n"
    "玩家在问问题（带问号、为什么/怎么/哪）且场景有 NPC 时，优先 talk。\n"
    "如果玩家说得很模糊，kind=unclear，并给一句 clarify（不超过 30 字，给具体选项）。"
)


class RuleIntentParser:
    """现有规则解析器的适配层（默认兜底）。"""

    async def parse(self, text: str, *, context: dict) -> IntentResult:
        action = parse_action(
            text,
            clues=[c["name"] for c in context.get("candidates", []) if c["type"] == "clue"],
            npcs=[c["name"] for c in context.get("candidates", []) if c["type"] == "npc"],
            exits=[c["name"] for c in context.get("candidates", []) if c["type"] == "exit"],
        )
        # 规则解析只要认出了动词就交给后续模糊匹配；只有 custom 才当听不懂
        confidence = 0.9 if action.type != "custom" else 0.3
        return IntentResult(
            kind=action.type,
            target=action.target,
            confidence=confidence,
            source="rule",
            raw=action.as_dict(),
        )


class LlmIntentParser:
    """模型解析 + 规则兜底。"""

    def __init__(self, client: LlmClient, fallback: IntentParser | None = None):
        self.client = client
        self.fallback = fallback or RuleIntentParser()

    async def parse(self, text: str, *, context: dict) -> IntentResult:
        candidates = context.get("candidates") or []
        user = (
            f"玩家原话：{text}\n"
            f"上一句 IC：{context.get('last_line') or '（无）'}\n"
            f"当前场景：{context.get('scene') or '未知'}\n"
            f"候选（id | 名称 | 别名 | 状态）：\n{_candidate_lines(candidates)}\n\n"
            "输出 JSON：{\"kind\": \"...\", \"target_id\": \"...\", \"approach\": \"...\", "
            "\"confidence\": 0.0, \"clarify\": \"...\"}"
        )
        data = await self.client.chat_json(SYSTEM, user, temperature=0.0, max_tokens=200)
        if not data:
            return await self.fallback.parse(text, context=context)

        kind = str(data.get("kind") or "").strip()
        target_id = str(data.get("target_id") or "").strip()
        try:
            confidence = float(data.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        valid_ids = {c["id"] for c in candidates} | {"unmatched", ""}
        if kind not in KINDS or target_id not in valid_ids:
            logger.info(f"[coc] 意图解析结果不可用，回退规则: kind={kind!r} target={target_id!r}")
            return await self.fallback.parse(text, context=context)

        target = target_id
        for item in candidates:
            if item["id"] == target_id:
                target = item["name"]
                break

        return IntentResult(
            kind=kind,
            target="" if target in ("unmatched", "") else target,
            approach=str(data.get("approach") or "").strip(),
            confidence=confidence,
            clarify=str(data.get("clarify") or "").strip(),
            source="llm",
            raw=data,
        )
