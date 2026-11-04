"""车卡向导：五步状态机（mode → occupation → attributes → skills → preview）。

纯文本多轮，不做卡片。所有数值在服务端计算与校验；玩家只做选择与微调。
草稿存 ``character_draft`` 表，30 分钟过期；任何一步都可以「取消」。
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from ..domain import (
    ATTRS,
    Investigator,
    POINT_BUY_MAX,
    POINT_BUY_MIN,
    POINT_BUY_TOTAL,
    auto_allocate_skills,
    base_skill_value,
    damage_bonus,
    default_skills,
    movement,
    get_occupation,
    hp_max,
    list_occupations,
    mp_max,
    random_investigator,
    san_max,
    validate_creation,
)
from ..domain.occupations import SPECIAL_SKILL_BASE

STEPS = ("mode", "occupation", "attributes", "skills", "preview")
STEP_TOTAL = len(STEPS)

ATTR_LABELS = {
    "STR": "力量", "CON": "体质", "SIZ": "体型", "DEX": "敏捷",
    "APP": "外貌", "INT": "智力", "POW": "意志", "EDU": "教育",
}
LABEL_TO_ATTR = {label: key for key, label in ATTR_LABELS.items()}

_YES = {"确认", "确定", "ok", "好", "是", "就这样"}
_CANCEL = {"取消", "退出", "算了"}


@dataclass
class WizardReply:
    text: str
    step: str
    done: bool = False
    character_id: int | None = None


def sheet_text(inv: Investigator) -> str:
    attrs = inv.attrs
    db_text, build = damage_bonus(attrs)
    skills = inv.effective_skills()
    shown = "、".join(f"{name} {skills.get(name, 0)}" for name in ("侦查", "聆听", "图书馆使用", "医学", "急救", "心理学") if name in skills)
    return (
        f"【调查员】{inv.name}（{inv.occupation}）\n"
        f"力量 {attrs.get('STR')}  体质 {attrs.get('CON')}  体型 {attrs.get('SIZ')}  敏捷 {attrs.get('DEX')}\n"
        f"外貌 {attrs.get('APP')}  智力 {attrs.get('INT')}  意志 {attrs.get('POW')}  教育 {attrs.get('EDU')}\n"
        f"HP {inv.hp}/{inv.hp_max}  MP {inv.mp}/{inv.mp_max}  SAN {inv.san}/{inv.san_max}  "
        f"MOV 8  DB {db_text}\n"
        f"技能：{shown}"
    )


def _parse_edit(text: str) -> tuple[str, str, int] | None:
    """解析「教育 -10」「力量 60」「侦查 +10」→ (token, sign, value)。"""
    match = re.match(r"^\s*([^\d\s+-]+)\s*([+-])?\s*(\d+)\s*$", text or "")
    if not match:
        return None
    return match.group(1), match.group(2) or "", int(match.group(3))


def _apply(current: int, sign: str, value: int) -> int:
    if sign == "+":
        return current + value
    if sign == "-":
        return current - value
    return value


class CharacterWizard:
    def __init__(self, store, rng: random.Random | None = None):
        self.store = store
        self.rng = rng or random.Random()

    # ---------------- 入口 ----------------

    def start(self, campaign_id: int, qq: int, *, name: str = "") -> WizardReply:
        draft = self.store.get_draft(campaign_id, qq)
        if draft is not None:
            payload = dict(draft.get("payload") or {})
            if name:
                payload["name"] = name
            self.store.save_draft(campaign_id, qq, draft["step"], payload)
            return WizardReply(
                f"继续上次车卡（第 {self._step_no(draft['step'])}/{STEP_TOTAL} 步）：\n"
                + self._prompt(draft["step"], payload),
                draft["step"],
            )

        existing = self.store.find_character_by_owner(campaign_id, qq)
        payload = {"name": name or "调查员"}
        self.store.save_draft(campaign_id, qq, "mode", payload)
        prefix = "（你已有一张角色卡，完成向导会覆盖它）\n" if existing else ""
        return WizardReply(prefix + self._mode_prompt(), "mode")

    def handle(self, campaign_id: int, qq: int, text: str) -> WizardReply:
        draft = self.store.get_draft(campaign_id, qq)
        if draft is None:
            return WizardReply("没有进行中的车卡流程，发 /coc 车卡 开始。", "none")
        if (text or "").strip() in _CANCEL:
            return self.cancel(campaign_id, qq)
        handler = {
            "mode": self._on_mode,
            "occupation": self._on_occupation,
            "attributes": self._on_attributes,
            "skills": self._on_skills,
            "preview": self._on_preview,
        }[draft["step"]]
        return handler(campaign_id, qq, dict(draft.get("payload") or {}), (text or "").strip())

    def cancel(self, campaign_id: int, qq: int) -> WizardReply:
        self.store.delete_draft(campaign_id, qq)
        return WizardReply("车卡已取消。", "none")

    # ---------------- 各步 ----------------

    def _on_mode(self, cid, qq, payload, text):
        mode = self._parse_mode(text)
        if mode is None:
            return WizardReply(self._mode_prompt(repeat=True), "mode")

        if mode == "random":
            inv = random_investigator(self.rng, name=payload.get("name") or "调查员")
            inv.creation = {"mode": "random", "source": "random"}
            char_id = self.store.save_character(cid, inv, owner_qq=qq, creation=inv.creation)
            self.store.delete_draft(cid, qq)
            return WizardReply("已生成随机调查员（老流程）：\n" + sheet_text(inv), "done", True, char_id)

        payload["mode"] = mode
        self._save(cid, qq, "occupation", payload)
        return WizardReply(self._occupation_prompt(), "occupation")

    def _on_occupation(self, cid, qq, payload, text):
        occupation = self._pick_occupation(text)
        if occupation is None:
            return WizardReply(self._occupation_prompt(repeat=True), "occupation")

        payload["occupation"] = occupation.key
        if payload.get("mode") == "quick":
            payload["attrs"] = self._roll_attrs()
            payload["reroll_used"] = False
        else:
            payload["attrs"] = occupation.template_attrs()
        self._save(cid, qq, "attributes", payload)
        return WizardReply(self._attrs_prompt(payload), "attributes")

    def _on_attributes(self, cid, qq, payload, text):
        occupation = get_occupation(payload.get("occupation"))
        if occupation is None:
            return WizardReply("职业数据丢了，重新选一次：\n" + self._occupation_prompt(), "occupation")

        if text.lower() in _YES:
            problems = self._attr_problems(payload)
            if problems:
                return WizardReply(
                    "属性还没配好：\n- " + "\n- ".join(problems) + "\n" + self._attrs_prompt(payload),
                    "attributes",
                )
            payload["skills"] = auto_allocate_skills(payload["attrs"], occupation)
            self._save(cid, qq, "skills", payload)
            return WizardReply(self._skills_prompt(payload), "skills")

        if text in ("重掷", "重投", "reroll"):
            if payload.get("mode") != "quick":
                return WizardReply(
                    "点数分配模式不需要重掷，直接用「力量 60」这种改法。\n" + self._attrs_prompt(payload),
                    "attributes",
                )
            if payload.get("reroll_used"):
                return WizardReply(
                    "已经重掷过一次了（规则只允许一次）。\n" + self._attrs_prompt(payload),
                    "attributes",
                )
            payload["attrs"] = self._roll_attrs()
            payload["reroll_used"] = True
            self._save(cid, qq, "attributes", payload)
            return WizardReply("重掷结果：\n" + self._attrs_prompt(payload), "attributes")

        edit = _parse_edit(text)
        key = self._attr_key(edit[0]) if edit else None
        if edit is None or key is None:
            return WizardReply(self._attrs_prompt(payload, repeat=True), "attributes")

        _, sign, value = edit
        payload["attrs"][key] = _apply(int(payload["attrs"].get(key, 0)), sign, value)
        self._save(cid, qq, "attributes", payload)
        return WizardReply(self._attrs_prompt(payload), "attributes")

    def _on_skills(self, cid, qq, payload, text):
        occupation = get_occupation(payload.get("occupation"))
        if occupation is None:
            return WizardReply("职业数据丢了，重新选一次：\n" + self._occupation_prompt(), "occupation")

        if text.lower() in _YES:
            report = self._report(payload, occupation)
            if not report.ok:
                return WizardReply(
                    "还不能确认：\n- " + "\n- ".join(report.problems) + "\n" + self._skills_prompt(payload, report),
                    "skills",
                )
            self._save(cid, qq, "preview", payload)
            return WizardReply(self._preview_text(payload, occupation, report), "preview")

        if text in ("重置", "推荐", "重来"):
            payload["skills"] = auto_allocate_skills(payload["attrs"], occupation)
            self._save(cid, qq, "skills", payload)
            return WizardReply("已恢复推荐分配。\n" + self._skills_prompt(payload), "skills")

        edit = _parse_edit(text)
        if edit is None:
            return WizardReply(self._skills_prompt(payload, repeat=True), "skills")

        token, sign, value = edit
        name = self._skill_name(token, payload, occupation)
        if name is None:
            return WizardReply(f"没有这个技能：{token}\n" + self._skills_prompt(payload), "skills")

        trial = dict(payload)
        trial["skills"] = dict(payload.get("skills") or {})
        current = int(trial["skills"].get(name, base_skill_value(name, payload["attrs"])))
        trial["skills"][name] = _apply(current, sign, value)
        report = self._report(trial, occupation)
        if not report.ok:
            return WizardReply(
                "这样改不行：\n- " + "\n- ".join(report.problems) + "\n" + self._skills_prompt(payload),
                "skills",
            )

        payload["skills"] = trial["skills"]
        self._save(cid, qq, "skills", payload)
        return WizardReply(self._skills_prompt(payload, report), "skills")

    def _on_preview(self, cid, qq, payload, text):
        occupation = get_occupation(payload.get("occupation"))
        if occupation is None:
            return WizardReply("职业数据丢了，重新选一次：\n" + self._occupation_prompt(), "occupation")

        if text.lower() in _YES:
            report = self._report(payload, occupation)
            if not report.ok:
                return WizardReply("属性/技能有变动，先回去改：\n- " + "\n- ".join(report.problems), "skills")
            inv = self._build(payload, occupation)
            char_id = self.store.save_character(cid, inv, owner_qq=qq, creation=inv.creation)
            self.store.delete_draft(cid, qq)
            return WizardReply("角色已入库：\n" + sheet_text(inv), "done", True, char_id)

        if text in ("改属性", "属性"):
            self._save(cid, qq, "attributes", payload)
            return WizardReply(self._attrs_prompt(payload), "attributes")
        if text in ("改技能", "技能"):
            self._save(cid, qq, "skills", payload)
            return WizardReply(self._skills_prompt(payload), "skills")
        if text in _CANCEL:
            return self.cancel(cid, qq)

        return WizardReply(self._preview_text(payload, occupation, self._report(payload, occupation)), "preview")

    # ---------------- 提示词 ----------------

    def _mode_prompt(self, repeat: bool = False) -> str:
        head = "第 1/5 步｜选择车卡方式" if not repeat else "没听明白，再选一次："
        return (
            f"{head}\n"
            "① 点数分配：460 点，单项 40-90（推荐，可控）\n"
            "② 快速骰点：3d6×5，命运感\n"
            "③ 随机一张：直接生成（老流程）\n"
            "回数字，或说「点数 / 快速 / 随机」"
        )

    def _occupation_prompt(self, repeat: bool = False) -> str:
        names = [occupation.name for occupation in list_occupations()]
        lines = "  ".join(f"{index}. {name}" for index, name in enumerate(names, 1))
        head = "第 2/5 步｜选择职业" if not repeat else "没听明白，再选一次："
        return f"{head}\n{lines}\n回序号或职业名。"

    def _attrs_prompt(self, payload: dict, repeat: bool = False) -> str:
        attrs = payload.get("attrs") or {}
        occupation = get_occupation(payload.get("occupation"))
        line = "  ".join(f"{ATTR_LABELS[key]} {attrs.get(key, 0)}" for key in ATTRS)
        total = sum(int(attrs.get(key, 0)) for key in ATTRS)
        head = "第 3/5 步｜属性" if not repeat else "没听明白，再改一次："
        if payload.get("mode") == "quick":
            tail = f"（合计 {total}）回「确认」；可以「重掷」一次。"
        else:
            diff = total - POINT_BUY_TOTAL
            gap = "" if diff == 0 else f"（{'多' if diff > 0 else '少'} {abs(diff)}）"
            tail = (
                f"（合计 {total} / {POINT_BUY_TOTAL}{gap}）回「确认」；"
                "改法：「教育 -10」「力量 60」。"
            )
        return f"{head}（{occupation.name if occupation else ''}）\n{line}\n{tail}"

    def _skills_prompt(self, payload: dict, report=None, repeat: bool = False) -> str:
        occupation = get_occupation(payload.get("occupation"))
        report = report or self._report(payload, occupation)
        skills = payload.get("skills") or {}
        shown = "、".join(f"{name} {value}" for name, value in list(skills.items())[:8])
        head = "第 4/5 步｜技能" if not repeat else "没听明白，再说一次："
        return (
            f"{head}\n{report.summary()}\n推荐分配：{shown}\n"
            "回「确认」；改：「侦查 80」或「侦查 +10」；「重置」恢复推荐。"
        )

    def _preview_text(self, payload: dict, occupation, report) -> str:
        inv = self._build(payload, occupation)
        return (
            "第 5/5 步｜预览\n" + sheet_text(inv) + "\n" + report.summary()
            + "\n回「确认」入库 /「改属性」/「改技能」/「取消」。"
        )

    def _prompt(self, step: str, payload: dict) -> str:
        occupation = get_occupation(payload.get("occupation"))
        if step == "mode":
            return self._mode_prompt()
        if step == "occupation":
            return self._occupation_prompt()
        if step == "attributes":
            return self._attrs_prompt(payload)
        if step == "skills":
            return self._skills_prompt(payload)
        report = self._report(payload, occupation) if occupation else None
        if report is None:
            return self._occupation_prompt()
        return self._preview_text(payload, occupation, report)

    # ---------------- 工具 ----------------

    def _save(self, cid: int, qq: int, step: str, payload: dict) -> None:
        self.store.save_draft(cid, qq, step, payload)

    @staticmethod
    def _step_no(step: str) -> int:
        return STEPS.index(step) + 1 if step in STEPS else 1

    @staticmethod
    def _parse_mode(text: str) -> str | None:
        lowered = text.lower()
        if lowered in ("1", "点数", "点数分配", "point", "point_buy", "buy"):
            return "point_buy"
        if lowered in ("2", "快速", "快速骰点", "quick", "骰"):
            return "quick"
        if lowered in ("3", "随机", "random"):
            return "random"
        return None

    @staticmethod
    def _pick_occupation(text: str):
        occupations = list_occupations()
        if text.isdigit():
            index = int(text) - 1
            if 0 <= index < len(occupations):
                return occupations[index]
            return None
        return get_occupation(text)

    @staticmethod
    def _attr_key(token: str) -> str | None:
        upper = token.upper()
        if upper in ATTRS:
            return upper
        return LABEL_TO_ATTR.get(token)

    @staticmethod
    def _skill_name(token: str, payload: dict, occupation) -> str | None:
        attrs = payload.get("attrs") or {}
        known = set(default_skills(attrs)) | set(occupation.skills)
        known |= set(payload.get("skills") or {}) | set(SPECIAL_SKILL_BASE)
        return token if token in known else None

    def _roll_attrs(self) -> dict:
        def roll_3d6() -> int:
            return sum(self.rng.randint(1, 6) for _ in range(3)) * 5

        def roll_2d6p6() -> int:
            return (sum(self.rng.randint(1, 6) for _ in range(2)) + 6) * 5

        return {
            "STR": roll_3d6(), "CON": roll_3d6(), "SIZ": roll_2d6p6(),
            "DEX": roll_3d6(), "APP": roll_3d6(), "INT": roll_2d6p6(),
            "POW": roll_3d6(), "EDU": roll_2d6p6(),
        }

    @staticmethod
    def _attr_problems(payload: dict) -> list[str]:
        attrs = payload.get("attrs") or {}
        problems: list[str] = []
        total = sum(int(attrs.get(key, 0)) for key in ATTRS)
        if payload.get("mode") == "quick":
            for key in ATTRS:
                value = int(attrs.get(key, 0))
                if not (15 <= value <= 90) or value % 5 != 0:
                    problems.append(f"{ATTR_LABELS[key]}={value} 不符合快速骰点（15-90，5 的倍数）")
            return problems
        for key in ATTRS:
            value = int(attrs.get(key, 0))
            if not (POINT_BUY_MIN <= value <= POINT_BUY_MAX):
                problems.append(f"{ATTR_LABELS[key]}={value} 超出 {POINT_BUY_MIN}-{POINT_BUY_MAX}")
        if total != POINT_BUY_TOTAL:
            diff = total - POINT_BUY_TOTAL
            problems.append(f"合计 {total}，需要正好 {POINT_BUY_TOTAL}（{'多' if diff > 0 else '少'} {abs(diff)}）")
        return problems

    def _report(self, payload: dict, occupation):
        attrs = {key: int((payload.get("attrs") or {}).get(key, 0)) for key in ATTRS}
        inv = Investigator(
            name=payload.get("name") or "调查员",
            occupation=occupation.name if occupation else "调查员",
            attrs=attrs,
            skills={name: int(value) for name, value in (payload.get("skills") or {}).items()},
        )
        return validate_creation(inv, occupation, mode=payload.get("mode", "point_buy"))

    def _build(self, payload: dict, occupation) -> Investigator:
        attrs = {key: int((payload.get("attrs") or {}).get(key, 0)) for key in ATTRS}
        skills = {name: int(value) for name, value in (payload.get("skills") or {}).items()}
        inv = Investigator(
            name=payload.get("name") or "调查员",
            occupation=occupation.name,
            attrs=attrs,
            skills=skills,
        )
        inv.state = {
            "hp": hp_max(attrs), "mp": mp_max(attrs), "san": san_max(attrs),
            "luck": 50,
        }
        inv.creation = {
            "mode": payload.get("mode", "point_buy"),
            "occupation": occupation.key,
            "source": "wizard",
            "attrs": dict(attrs),
            "skills": dict(skills),
        }
        return inv
