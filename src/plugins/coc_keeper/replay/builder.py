"""复盘：从事件表重放生成战报（Markdown）。

不依赖模型，纯事实：事件时间线 + 骰点表 + 线索 + 统计。
事件表是 append-only 的，所以同一局可以反复重放、样式可以独立演进。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..module.model import module_from_row

OUTCOME_LABEL = {
    "critical": "大成功",
    "extreme": "极难成功",
    "hard": "困难成功",
    "regular": "成功",
    "failure": "失败",
    "fumble": "大失败",
}

ACTION_LABEL = {
    "investigate": "调查",
    "talk": "交谈",
    "move": "移动",
    "attack": "攻击",
    "dodge": "闪避",
    "use_item": "使用物品",
    "skill_check": "检定",
    "wait": "等待",
    "custom": "自由行动",
}


@dataclass
class ReplayReport:
    session_id: int
    title: str
    markdown: str
    stats: dict = field(default_factory=dict)


def _format_time(value: str | None) -> str:
    return (value or "").replace("T", " ")


def build_replay(store, session_id: int) -> ReplayReport:
    session = store.get_session(session_id)
    if session is None:
        raise ValueError(f"会话不存在: {session_id}")

    campaign = store.get_campaign(int(session["campaign_id"])) or {}
    module_row = store.get_module(int(campaign["module_id"])) if campaign.get("module_id") else None
    module = module_from_row(module_row) if module_row else None
    title = module.title if module else "未知模组"

    events = store.list_events(session_id, limit=2000)
    rolls = store.list_rolls(session_id)
    clues = store.discovered_clues(session_id)

    # 行动者显示名：QQ → 角色名
    names = {}
    for char in store.list_characters(int(session["campaign_id"])):
        if char.get("owner_qq"):
            names[str(char["owner_qq"])] = char["name"]
    for clue in clues:
        if clue.get("discovered_by") and clue["discovered_by"] not in names:
            names[clue["discovered_by"]] = clue["discovered_by"]

    def who(actor: str | None) -> str:
        if not actor or actor == "system":
            return "KP"
        return names.get(str(actor), str(actor))

    def clue_name(clue_id: str | None) -> str:
        if not clue_id:
            return "?"
        if module and module.clue(clue_id):
            return module.clue(clue_id).name
        return clue_id

    # ---- 时间线 ----
    timeline: list[str] = []
    for event in events:
        payload = event.get("payload") or {}
        kind = event.get("type")
        if kind == "scene_enter":
            scene_id = payload.get("scene", "?")
            scene_title = module.scene(scene_id).title if module and scene_id in module.scenes else scene_id
            timeline.append(f"- 进入场景 **{scene_title}**")
        elif kind == "action":
            action = payload.get("action") or {}
            label = ACTION_LABEL.get(action.get("type"), action.get("type") or "行动")
            target = action.get("target") or ""
            narrative = (payload.get("narrative") or "").splitlines()
            first_line = narrative[0] if narrative else ""
            timeline.append(f"- {who(event.get('actor'))} {label}{target}：{first_line}")
        elif kind == "clue_found":
            timeline.append(f"- 发现线索 **{clue_name(payload.get('clue'))}**")
        elif kind == "keeper_mercy":
            reason = payload.get("reason") or "mercy"
            timeline.append(f"- （KP 调控）{reason}")
        elif kind == "character_import":
            timeline.append(f"- 导入角色 {payload.get('name') or ''}".strip())
        elif kind == "session_end":
            ending = payload.get("ending") or "?"
            timeline.append(f"- **本局结束**（结局：{ending}）")

    # ---- 骰点表 ----
    roll_lines = [
        "| # | 行动者 | 技能 | 目标 | d100 | 结果 | 可见性 |",
        "|---|---|---|---|---|---|---|",
    ]
    success = 0
    for index, roll in enumerate(rolls, 1):
        outcome = roll.get("outcome") or ""
        if outcome in ("critical", "extreme", "hard", "regular"):
            success += 1
        roll_lines.append(
            f"| {index} | {who(roll.get('actor'))} | {roll.get('skill') or '-'} | "
            f"{roll.get('target') if roll.get('target') is not None else '-'} | "
            f"{roll.get('d100') if roll.get('d100') is not None else '-'} | "
            f"{OUTCOME_LABEL.get(outcome, outcome or '-')} | {roll.get('visibility') or 'public'} |"
        )
    if not rolls:
        roll_lines.append("| - | - | - | - | - | 本局没有掷骰 | - |")

    # ---- 线索 / 统计 ----
    clue_lines = []
    total_clues = len(module.clues) if module else 0
    for clue in clues:
        clue_id = clue.get("clue_id")
        obj = module.clue(clue_id) if module else None
        name = obj.name if obj else clue_id
        importance = obj.importance if obj else "?"
        clue_lines.append(f"- {name}（{importance}）")
    if not clue_lines:
        clue_lines.append("- （本局没有发现线索）")

    turns = int(session.get("turn_no") or 0)
    stats = {
        "turns": turns,
        "events": len(events),
        "rolls": len(rolls),
        "success_rate": round(success / len(rolls) * 100, 1) if rolls else 0.0,
        "clues_found": len(clues),
        "clues_total": total_clues,
        "clue_rate": round(len(clues) / total_clues * 100, 1) if total_clues else 0.0,
        "ending": (store.get_session_state(session_id) or {}).get("ended"),
    }

    markdown = "\n".join(
        [
            f"# {title} · 战报",
            "",
            f"- 时间：{_format_time(session.get('started_at'))} → {_format_time(session.get('ended_at')) or '进行中'}",
            f"- 回合数：{turns}｜事件：{len(events)}｜掷骰：{len(rolls)}（成功率 {stats['success_rate']}%）",
            f"- 线索：{len(clues)}/{total_clues}（{stats['clue_rate']}%）｜结局：{stats['ending'] or '未结束'}",
            "",
            "## 时间线",
            "",
            "\n".join(timeline) if timeline else "- （还没有事件）",
            "",
            "## 骰点",
            "",
            "\n".join(roll_lines),
            "",
            "## 已发现线索",
            "",
            "\n".join(clue_lines),
            "",
            f"> 由 coc_keeper 于 {datetime.now().strftime('%Y-%m-%d %H:%M')} 自动生成。",
            "",
        ]
    )
    return ReplayReport(session_id=session_id, title=title, markdown=markdown, stats=stats)


def save_replay(report: ReplayReport, directory: str | Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"session_{report.session_id}.md"
    path.write_text(report.markdown, encoding="utf-8")
    return path
