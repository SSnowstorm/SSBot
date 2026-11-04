"""连续性记忆：最近对话 + 滚动摘要。

- 最近对话：引擎每回合写进 ``session.state_json["recent"]``（玩家/守秘人各一条）
- 滚动摘要：每 N 回合让模型把最近对话压成 3-5 句事实摘要，写回 ``state["summary"]``
  失败就保留旧摘要，不阻塞跑团
"""

from __future__ import annotations

from .client import LlmClient

SUMMARY_EVERY = 10
MAX_RECENT = 16

SYSTEM = (
    "你在为跑团整理“到目前为止发生了什么”的摘要。只输出 3-5 句客观事实，"
    "不要评价、不要编造、不要写规则或骰点。"
)


def recent_context(state: dict, limit: int = 6) -> list[dict]:
    return (state.get("recent") or [])[-limit:]


def append_turn(state: dict, player_text: str, keeper_text: str) -> None:
    recent = state.setdefault("recent", [])
    recent.append({"role": "player", "text": (player_text or "").strip()[:200]})
    recent.append({"role": "keeper", "text": (keeper_text or "").strip()[:300]})
    if len(recent) > MAX_RECENT:
        del recent[:-MAX_RECENT]


def format_recent(recent: list[dict]) -> str:
    lines = []
    for item in recent:
        who = "玩家" if item.get("role") == "player" else "守秘人"
        lines.append(f"{who}：{item.get('text') or ''}")
    return "\n".join(lines)


async def maybe_summarize(
    client: LlmClient | None,
    state: dict,
    turn_no: int,
    *,
    every: int = SUMMARY_EVERY,
) -> bool:
    """每 N 回合更新一次摘要；返回是否更新成功。"""
    if not client or not client.available:
        return False
    if turn_no <= 0 or turn_no % every != 0:
        return False
    recent = recent_context(state, limit=MAX_RECENT)
    if not recent:
        return False
    user = (
        f"已有的摘要：{state.get('summary') or '（无）'}\n"
        f"最近的回合：\n{format_recent(recent)}\n\n"
        "请输出合并后的新摘要（3-5 句）。"
    )
    text = await client.chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        temperature=0.3,
        max_tokens=220,
    )
    if not text:
        return False
    state["summary"] = text.strip()[:500]
    return True
