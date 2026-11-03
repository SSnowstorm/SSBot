"""运行时：动作解析、场景状态机、叙事适配。"""

from .actions import ACTION_TYPES, Action, parse_action
from .engine import ActResult, CocRuntime
from .narrator import LlmNarrator, Narrator, TemplateNarrator, build_narrator

__all__ = [
    "ACTION_TYPES", "Action", "parse_action",
    "ActResult", "CocRuntime",
    "LlmNarrator", "Narrator", "TemplateNarrator", "build_narrator",
]
