"""自然语言 → 结构化动作（P1 规则版，模型兜底留到 P2）。

动作类型是闭集：investigate / move / talk / attack / dodge / use_item / skill_check / wait / custom
解析不出来的返回 ``custom``（调用方应当反问，而不是猜）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

ACTION_TYPES = (
    "investigate", "move", "talk", "attack", "dodge",
    "use_item", "skill_check", "wait", "custom",
)

# 动词表顺序有意义：先匹配更具体的
_VERB_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("搜查", "检查", "查看", "观察", "翻找", "翻", "调查", "找", "看看", "看"), "investigate"),
    (("交谈", "搭话", "打听", "追问", "说服", "问"), "talk"),
    (("前往", "进入", "走向", "走到", "回到", "去", "回"), "move"),
    (("开枪", "射击", "攻击", "砍", "打"), "attack"),
    (("闪避", "回避", "躲"), "dodge"),
    (("点燃", "泼", "砸", "使用", "用"), "use_item"),
    (("等待", "观望", "不动", "等"), "wait"),
)

# 句首的口语前缀，先剥掉再匹配
_PREFIXES = ("我想", "我要", "我打算", "我准备", "想要", "打算", "我")
_TRIM = " ，,。.！!？?：:、\"“”‘’「」"

# 「和某人说话」句式（先于动词表处理）
_TALK_RE = re.compile(r"^(?:和|跟|与)(.+?)(?:说话|搭话|交谈|聊聊|聊)")


@dataclass
class Action:
    type: str
    target: str
    raw: str
    confident: bool = True

    def as_dict(self) -> dict:
        return {"type": self.type, "target": self.target, "raw": self.raw, "confident": self.confident}


def _strip_prefixes(text: str) -> str:
    changed = True
    while changed:
        changed = False
        for prefix in _PREFIXES:
            if text.startswith(prefix) and len(text) > len(prefix):
                text = text[len(prefix):].lstrip(_TRIM)
                changed = True
    return text


def _best_match(text: str, candidates: Iterable[str]) -> str:
    """在候选名里找最长命中（包含关系即可）。"""
    best = ""
    for name in candidates:
        if not name:
            continue
        if name in text or text in name:
            if len(name) > len(best):
                best = name
    return best


def parse_action(
    raw: str,
    *,
    clues: Iterable[str] = (),
    npcs: Iterable[str] = (),
    exits: Iterable[str] = (),
) -> Action:
    """把玩家的一句话解析成动作。

    Args:
        raw: 玩家原话
        clues: 当前场景可调查对象名（线索名）
        npcs: 当前场景 NPC 名
        exits: 当前场景出口名
    """
    text = (raw or "").strip(_TRIM)
    text = _strip_prefixes(text)
    if not text:
        return Action("custom", "", raw or "", confident=False)

    # 「和/跟/与 X 说话」这类句式先单独处理，避免被动词表漏掉
    talk_match = _TALK_RE.match(text)
    if talk_match:
        return Action("talk", talk_match.group(1).strip(_TRIM), raw.strip(), confident=True)

    candidates = {"investigate": list(clues), "talk": list(npcs), "move": list(exits)}

    for verbs, kind in _VERB_RULES:
        for verb in verbs:
            if text.startswith(verb):
                rest = text[len(verb):].strip(_TRIM)
                target = _best_match(rest, candidates.get(kind, [])) if rest else ""
                return Action(kind, target or rest, raw.strip(), confident=bool(target or kind in ("wait",)))
    return Action("custom", text, raw.strip(), confident=False)