"""LLM 层：客户端、意图解析、NPC 台词。

全部实现都遵守「失败返回 None / 回退确定性实现」，不阻塞跑团流程。
"""

from .client import LlmClient
from .intent import IntentParser, IntentResult, KINDS, MIN_CONFIDENCE, LlmIntentParser, RuleIntentParser
from .guard import GuardResult, check as guard_check, leaks as guard_leaks
from .keeper import DialogueWriter, LlmDialogueWriter, NpcLineRequest, TemplateDialogueWriter
from .memory import append_turn, maybe_summarize, recent_context

__all__ = [
    "LlmClient",
    "IntentParser", "IntentResult", "KINDS", "MIN_CONFIDENCE", "LlmIntentParser", "RuleIntentParser",
    "DialogueWriter", "LlmDialogueWriter", "NpcLineRequest", "TemplateDialogueWriter",
    "GuardResult", "guard_check", "guard_leaks",
    "append_turn", "maybe_summarize", "recent_context",
]
