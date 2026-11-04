"""场景状态机 + 行动结算（P1）。

一次 ``act`` 的流程：
    解析动作 → 合法性 → 检定（可选）→ 状态变更 → 线索/场景/结局 → 事实包 → 叙事

状态只落在两处：``session.state_json``（场景/张紧度/是否结束）与 ``clue_state`` 表（已发现线索）。
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from nonebot.log import logger

from ..domain import (
    Difficulty,
    Investigator,
    Weapon,
    damage_bonus,
    resolve,
    resolve_attack,
    roll,
    roll_indefinite_madness,
    roll_temporary_madness,
    sanity_check,
    weapon_by_name,
)
from ..module.model import Clue, Module, Npc, Scene, module_from_row
from .actions import Action, parse_action
from .llm import (MIN_CONFIDENCE, IntentResult, LlmClient, NpcLineRequest, RuleIntentParser, TemplateDialogueWriter)
from .llm.memory import append_turn, maybe_summarize
from .narrator import Narrator, TemplateNarrator
from .style import StyleProfile, get_style


def _text_leaks(text: str, secret: str, n: int = 6) -> bool:
    """粗粒度剧透检测：共享任意 6 字片段即视为泄漏（fail-closed）。"""
    if not text or not secret:
        return False
    clean_text = re.sub(r"\s+", "", text)
    clean_secret = re.sub(r"\s+", "", secret)
    if len(clean_secret) < n:
        return clean_secret in clean_text
    grams = {clean_secret[i:i + n] for i in range(len(clean_secret) - n + 1)}
    return any(gram in clean_text for gram in grams)


@dataclass
class ActResult:
    narrative: str
    state: dict
    kind: str
    action: Action | None = None
    check: object | None = None
    clue: str | None = None
    ended: bool = False


class CocRuntime:
    """一局游戏的运行时；一局一个实例即可（无跨局状态）。"""

    def __init__(
        self,
        store,
        narrator: Narrator | None = None,
        rng: random.Random | None = None,
        intent_parser=None,
        dialogue=None,
        summarizer=None,
    ):
        self.store = store
        self.narrator = narrator or TemplateNarrator()
        self.rng = rng or random.Random()
        self.intent = intent_parser or RuleIntentParser()
        self.dialogue = dialogue or TemplateDialogueWriter()
        self.summarizer = summarizer

    # ---------------- 模组 ----------------

    def _module(self, campaign_id: int) -> Module:
        campaign = self.store.get_campaign(campaign_id)
        if not campaign or not campaign.get("module_id"):
            raise RuntimeError("这个团还没有绑定模组")
        row = self.store.get_module(int(campaign["module_id"]))
        if not row:
            raise RuntimeError("模组记录丢失")
        return module_from_row(row)

    # ---------------- 开局 ----------------

    async def start(self, campaign_id: int, module_id: int = 0, *, actor: str = "system") -> ActResult:
        if module_id:
            self.store.set_campaign_module(campaign_id, int(module_id))
        module = self._module(campaign_id)
        session = self.store.find_running_session(campaign_id)
        if session is None:
            session_id = self.store.create_session(campaign_id)
        else:
            session_id = int(session["id"])

        scene = module.scene(module.first_scene)
        state = {
            "scene": scene.id,
            "tension": 0,
            "ended": None,
            "visited": [scene.id],
        }
        self.store.update_session(session_id, scene=scene.id, turn_no=0)
        self.store.update_session_state(session_id, state)
        self.store.append_event(session_id, "scene_enter", actor=actor, payload={"scene": scene.id})

        narrative = await self._enter_scene(session_id, module, scene, state)
        logger.info(f"[coc] 开局 campaign={campaign_id} session={session_id} scene={scene.id}")
        return ActResult(narrative=narrative, state=state, kind="scene")

    # ---------------- 行动 ----------------

    async def act(self, session_id: int, qq: int, text: str) -> ActResult:
        session = self.store.get_session(session_id)
        if session is None:
            return ActResult("这局不存在。", {}, "notice")
        state = self.store.get_session_state(session_id)
        if state.get("ended"):
            return ActResult("这一局已经结束了，可以用 /coc 复盘 查看记录。", state, "notice")

        campaign_id = int(session["campaign_id"])
        module = self._module(campaign_id)
        scene = module.scene(state.get("scene") or module.first_scene)

        found = self.store.find_character_by_owner(campaign_id, int(qq))
        if found is None:
            return ActResult("你还没有调查员，先发 /coc 车卡。", state, "notice")
        _, inv = found

        candidates = self._build_candidates(module, scene, session_id)
        intent = await self._parse_intent(text, state, scene, candidates)
        if intent.kind in ("unclear", "custom") or intent.confidence < MIN_CONFIDENCE:
            clarify = intent.clarify or self._clarify_text(module, scene)
            narrative = await self._narrate(session_id, module, scene, "clarify", state=state, text=clarify)
            result = ActResult(narrative, state, "clarify")
            # 反问也算一次“卡住”：继续累计 idle，必要时给软提示
            result = await self._after_action(session_id, module, scene, result)
            self.store.update_session_state(session_id, state)
            return result

        action = Action(type=intent.kind, target=intent.target, raw=text.strip(), confident=True)
        state["last_ic"] = text.strip()[:120]
        self.store.append_event(
            session_id, "intent", actor=str(qq),
            payload={"kind": intent.kind, "target": intent.target, "source": intent.source,
                     "confidence": intent.confidence, "approach": intent.approach},
        )

        result = await self._dispatch(session_id, module, scene, inv, action, state, qq)
        result = await self._after_action(session_id, module, scene, result)

        # 回合推进 + 记录
        turn_no = int(session.get("turn_no") or 0) + 1
        append_turn(state, text, result.narrative)
        await maybe_summarize(self.summarizer, state, turn_no)
        self.store.update_session(session_id, turn_no=turn_no)
        self.store.update_session_state(session_id, result.state)
        self.store.append_event(
            session_id, "action", actor=str(qq),
            payload={"action": action.as_dict(), "scene": scene.id, "narrative": result.narrative[:200]},
        )

        ending = self._match_ending(module, action, result.state, session_id)
        if ending is not None:
            result.state["ended"] = ending.get("id")
            self.store.update_session_state(session_id, result.state)
            self.store.append_event(session_id, "session_end", actor=str(qq), payload={"ending": ending.get("id")})
            result.narrative = await self._narrate(
                session_id, module, scene, "ending", state=result.state,
                text=ending.get("text") or "", ending_id=ending.get("id"),
            )
            result.ended = True
            result.kind = "ending"

        return result

    # ---------------- 意图与场景 ----------------

    def _style_for(self, session_id: int) -> StyleProfile:
        session = self.store.get_session(session_id) or {}
        campaign = self.store.get_campaign(int(session.get("campaign_id") or 0)) or {}
        return get_style(campaign.get("keeper_style"))

    async def _narrate(self, session_id, module, scene, kind, *, state=None, **fields) -> str:
        """统一叙事入口：注入玩家可见上下文与 forbidden（守卫用，不发给模型）。"""
        state = state if state is not None else self.store.get_session_state(session_id)
        discovered = []
        for row in self.store.discovered_clues(session_id):
            clue = module.clue(row["clue_id"])
            if clue is not None:
                discovered.append(clue.name)

        forbidden = []
        for clue in module.clues.values():
            if not self.store.has_clue(session_id, clue.id):
                forbidden.append(clue.player_text)
            if clue.keeper_text:
                forbidden.append(clue.keeper_text)
        for candidate_scene in module.scenes.values():
            if candidate_scene.keeper_text:
                forbidden.append(candidate_scene.keeper_text)

        packet = {
            "kind": kind,
            "scene": {"id": scene.id, "title": scene.title, "player_text": scene.player_text},
            "discovered": discovered,
            "forbidden": forbidden,
            "recent": (state.get("recent") or [])[-6:],
            "summary": state.get("summary") or "",
        }
        style = self._style_for(session_id)
        packet["style"] = {"key": style.key, "label": style.label, "narration": style.narration}
        packet.update(fields)

        text = await self.narrator.narrate(packet)
        meta = getattr(self.narrator, "last_meta", None)
        if meta and not meta.get("passthrough"):
            self.store.append_event(session_id, "llm_call", actor="system", payload=meta)
        return text

    def _build_candidates(self, module: Module, scene: Scene, session_id: int) -> list[dict]:
        """当前场景玩家能感知到的实体（给意图解析与反问用）。"""
        items: list[dict] = []
        for clue in module.scene_clues(scene.id):
            items.append({
                "id": clue.id, "type": "clue", "name": clue.name,
                "aliases": list(clue.aliases or []),
                "state": "discovered" if self.store.has_clue(session_id, clue.id) else "undiscovered",
            })
        for npc in module.scene_npcs(scene.id):
            items.append({
                "id": npc.id, "type": "npc", "name": npc.name,
                "aliases": list(npc.aliases or []), "state": "present",
            })
        for exit_ in scene.exits:
            label = exit_.label or module.scene(exit_.to).title
            condition = exit_.condition or {}
            locked = bool(condition.get("clue")) and not self.store.has_clue(session_id, condition["clue"])
            items.append({
                "id": f"exit_{exit_.to}", "type": "exit", "name": label,
                "aliases": [], "state": "locked" if locked else "open",
            })
        return items

    async def _parse_intent(self, text: str, state: dict, scene: Scene, candidates: list[dict]) -> IntentResult:
        context = {
            "text": text,
            "scene": scene.title,
            "last_line": state.get("last_ic") or "",
            "candidates": candidates,
        }
        try:
            return await self.intent.parse(text, context=context)
        except Exception as exc:
            logger.warning(f"[coc] 意图解析异常，按听不懂处理: {exc!r}")
            return IntentResult(kind="unclear", confidence=0.0)

    def _clarify_text(self, module: Module, scene: Scene) -> str:
        options: list[str] = []
        for clue in module.scene_clues(scene.id)[:2]:
            options.append(f"再仔细看看「{clue.name}」")
        for npc in module.scene_npcs(scene.id)[:1]:
            options.append(f"问问{npc.name}")
        for exit_ in scene.exits[:1]:
            label = exit_.label or module.scene(exit_.to).title
            options.append(label if label.startswith(("去", "回", "前往")) else f"去{label}")
        if not options:
            return "你想做什么？说得具体一点，我来推进。"
        return "你想做什么？比如：" + "，或者".join(options) + "。"

    async def _env(self, session_id, module, scene, action, state) -> ActResult:
        seen = state.setdefault("details_seen", {}).setdefault(scene.id, [])
        remaining = [i for i in range(len(scene.details)) if i not in seen]
        if not remaining:
            return ActResult("这里你已经看得很仔细了，没有更多可看的。", state, "env", action)
        index = remaining[0]
        seen.append(index)
        text = scene.details[index]
        narrative = await self._narrate(session_id, module, scene, "env", state=state, text=text)
        return ActResult(narrative, state, "env", action)

    async def _dispatch(
        self,
        session_id: int,
        module: Module,
        scene: Scene,
        inv: Investigator,
        action: Action,
        state: dict,
        qq: int,
    ) -> ActResult:
        kind = action.type

        if kind == "investigate":
            return await self._investigate(session_id, module, scene, inv, action, state, qq)
        if kind == "talk":
            return await self._talk(session_id, module, scene, action, state, qq)
        if kind == "env":
            return await self._env(session_id, module, scene, action, state)
        if kind == "move":
            return await self._move(session_id, module, scene, action, state, qq)
        if kind in ("use_item", "attack", "dodge", "skill_check", "wait"):
            return await self._simple(session_id, module, scene, inv, action, state, qq)

        return ActResult(
            narrative=await self._narrate(
                session_id, module, scene, "clarify", state=state,
                text="我没太听明白。你是想搜查、问人，还是去别的地方？",
            ),
            state=state,
            kind="clarify",
            action=action,
        )

    # ---------------- 具体动作 ----------------

    async def _investigate(self, session_id, module, scene, inv, action, state, qq) -> ActResult:
        clue = self._match_clue(module, scene, action.target)
        if clue is None:
            return ActResult("你检查了一圈，没有发现更多东西。", state, "investigate", action)

        if self.store.has_clue(session_id, clue.id):
            return ActResult(f"关于「{clue.name}」你已经查过了。", state, "investigate", action)

        condition = clue.discover_condition or {}
        skill_name = condition.get("skill")
        if not skill_name:
            return await self._discover(session_id, module, scene, clue, state, action, qq, check=None)

        difficulty = Difficulty.parse(condition.get("difficulty", "regular"))
        check = resolve(skill_name, inv.skill_value(skill_name), difficulty, rng=self.rng)
        self.store.append_roll(
            session_id, actor=str(qq), kind="check", skill=skill_name,
            target=check.target, difficulty=check.difficulty.value,
            bonus_penalty=check.bonus - check.penalty,
            d100_value=check.roll, outcome=check.outcome.value, detail=check.detail,
        )
        if check.success:
            return await self._discover(session_id, module, scene, clue, state, action, qq, check=check)

        narrative = await self._narrate(
            session_id, module, scene, "check_fail", state=state,
            check={"skill": skill_name, "roll": check.roll, "target": check.target},
        )
        return ActResult(narrative, state, "investigate", action, check=check)

    async def _discover(self, session_id, module, scene, clue: Clue, state, action, qq, *, check) -> ActResult:
        self.store.discover_clue(session_id, clue.id, by=str(qq), scene_id=clue.scene)
        self.store.append_event(
            session_id, "clue_found", actor=str(qq), payload={"clue": clue.id, "scene": clue.scene}
        )
        # 线索可能提升张力（关键线索给压力）
        state["tension"] = min(100, int(state.get("tension", 0)) + (10 if clue.importance == "main" else 5))
        narrative = await self._narrate(
            session_id, module, scene, "clue", state=state,
            clue={"name": clue.name, "player_text": clue.player_text},
        )
        return ActResult(narrative, state, "clue", action, check=check, clue=clue.id)

    async def _talk(self, session_id, module, scene, action, state, qq) -> ActResult:
        npc = self._match_npc(module, scene, action.target)
        if npc is None:
            return ActResult("这里没有可以搭话的人。", state, "talk", action)

        clue = module.clue(npc.gives_clue) if npc.gives_clue else None
        can_reveal = clue is not None and not self.store.has_clue(session_id, clue.id)
        reveal_text = clue.player_text if (clue is not None and can_reveal) else ""

        request = NpcLineRequest(
            name=npc.name,
            identity=str(npc.public.get("identity") or ""),
            attitude=str(npc.public.get("attitude") or ""),
            voice=str(npc.public.get("voice") or ""),
            question=action.raw or action.target,
            reveal_text=reveal_text,
            answers=dict(npc.answers or {}),
            lines=list(npc.lines or []),
        )
        line = (await self.dialogue.write(request, rng=self.rng)) or ""
        if not line:
            line = f"{npc.name}看了你一眼，没有接话。"

        # 守卫：本轮不允许透露线索时，不得把线索原文漏出去
        if clue is not None and not can_reveal and _text_leaks(line, clue.player_text):
            line = f"{npc.name}看了你一眼，没有接话。"

        if can_reveal and clue is not None:
            self.store.discover_clue(session_id, clue.id, by=str(qq), scene_id=clue.scene)
            self.store.append_event(
                session_id, "clue_found", actor=str(qq), payload={"clue": clue.id, "via": npc.id}
            )

        narrative = await self._narrate(
            session_id, module, scene, "npc", state=state,
            npc={"name": npc.name, "line": line}, clue_text=reveal_text,
        )
        return ActResult(narrative, state, "talk", action)

    async def _move(self, session_id, module, scene, action, state, qq) -> ActResult:
        exit_ = self._match_exit(module, scene, action.target)
        if exit_ is None:
            return ActResult("那边没有路，或者你没找对方向。", state, "move", action)

        condition = exit_.condition or {}
        needed = condition.get("clue")
        if needed and not self.store.has_clue(session_id, needed):
            clue = module.clue(needed)
            hint = f"（也许该先查明「{clue.name}」）" if clue else ""
            return ActResult(
                await self._narrate(
                    session_id, module, scene, "blocked", state=state,
                    text=f"这条路现在还走不通。{hint}",
                ),
                state, "move", action,
            )

        target_scene = module.scene(exit_.to)
        state["scene"] = target_scene.id
        state.setdefault("visited", []).append(target_scene.id)
        self.store.update_session(session_id, scene=target_scene.id)
        self.store.append_event(
            session_id, "scene_enter", actor=str(qq), payload={"scene": target_scene.id}
        )
        narrative = await self._enter_scene(session_id, module, target_scene, state)
        return ActResult(narrative, state, "scene", action)

    async def _simple(self, session_id, module, scene, inv, action, state, qq) -> ActResult:
        if action.type == "wait":
            state["tension"] = min(100, int(state.get("tension", 0)) + 5)
            return ActResult(
                await self._narrate(
                    session_id, module, scene, "wait", state=state,
                    text="你们在原地等了一会儿，雾更浓了。",
                ),
                state, "wait", action,
            )
        if action.type == "skill_check":
            skill_name = action.target or "侦查"
            check = resolve(skill_name, inv.skill_value(skill_name), Difficulty.REGULAR, rng=self.rng)
            self.store.append_roll(
                session_id, actor=str(qq), kind="check", skill=skill_name,
                target=check.target, difficulty=check.difficulty.value,
                d100_value=check.roll, outcome=check.outcome.value, detail=check.detail,
            )
            return ActResult(f"🎲 {check.summary()}", state, "check", action, check=check)
        if action.type == "use_item":
            return ActResult(
                "你试着这么做，但眼下的东西没什么反应。", state, "use_item", action
            )
        return ActResult("你摆开了架势，但这里暂时没有需要动手的对象。", state, action.type, action)

    # ---------------- 卡关兜底 ----------------

    async def _after_action(self, session_id: int, module: Module, scene: Scene, result: ActResult) -> ActResult:
        """行动后检查是否卡关：先软提示（1 次/场景），再世界推进（1 次/场景）。

        设计文档 6.8.1：世界推进不是放水，不占放水配额，但必须可见。
        """
        state = result.state
        progressed = bool(result.clue) or result.kind in ("scene", "ending")
        if progressed:
            state["idle_turns"] = 0
            return result

        state["idle_turns"] = int(state.get("idle_turns", 0)) + 1
        idle = int(state["idle_turns"])
        style = self._style_for(session_id)

        if idle >= style.hint_at and not state.get(f"hint_{scene.id}"):
            hint = self._soft_hint(module, scene, session_id)
            if hint:
                state[f"hint_{scene.id}"] = True
                state["tension"] = min(100, int(state.get("tension", 0)) + 5)
                self.store.append_event(
                    session_id, "keeper_mercy", actor="system",
                    payload={"reason": "soft_hint", "scene": scene.id},
                )
                result.narrative = f"{result.narrative}\n\n{style.hint_prefix}{hint}"
                return result

        if idle >= style.tick_at and not state.get(f"tick_{scene.id}"):
            state[f"tick_{scene.id}"] = True
            state["tension"] = min(100, int(state.get("tension", 0)) + 10)
            self.store.append_event(
                session_id, "world_tick", actor="system",
                payload={"scene": scene.id, "idle": idle},
            )
            result.narrative = (
                f"{result.narrative}\n\n（时间在走）港口方向传来一声闷响，雾又浓了一分。"
            )
        return result

    def _soft_hint(self, module: Module, scene: Scene, session_id: int) -> str:
        undiscovered = [
            clue for clue in module.scene_clues(scene.id)
            if not self.store.has_clue(session_id, clue.id)
        ]
        main = [clue for clue in undiscovered if clue.importance == "main"] or undiscovered
        if main:
            clue = main[0]
            return f"你总觉得「{clue.name}」还有没看清的地方，也许该再仔细检查一次。"
        # 本场景已经没有可查的了：提示换场景，而不是让玩家干耗
        if scene.exits:
            exit_ = scene.exits[0]
            label = exit_.label or module.scene(exit_.to).title
            return f"这里能看的似乎都看过了，也许该{label}。"
        return ""

    # ---------------- 战斗 / 理智 ----------------

    def _npc_state(self, state: dict, npc) -> dict:
        table = state.setdefault("npc_hp", {})
        if npc.id not in table:
            hp = int(npc.stats.get("HP", 10) or 10)
            table[npc.id] = {"hp": hp, "max": hp, "dead": False}
        return table[npc.id]

    async def attack(self, session_id: int, qq: int, target: str, weapon_name: str = "") -> ActResult:
        session = self.store.get_session(session_id)
        if session is None:
            return ActResult("这局不存在。", {}, "notice")
        state = self.store.get_session_state(session_id)
        if state.get("ended"):
            return ActResult("这一局已经结束了。", state, "notice")

        campaign_id = int(session["campaign_id"])
        module = self._module(campaign_id)
        scene = module.scene(state.get("scene") or module.first_scene)
        found = self.store.find_character_by_owner(campaign_id, int(qq))
        if found is None:
            return ActResult("你还没有调查员，先发 /coc 车卡。", state, "notice")
        char_id, inv = found

        npc = self._match_npc(module, scene, target)
        if npc is None:
            return ActResult("这里没有你要攻击的对象。", state, "combat")

        npc_state = self._npc_state(state, npc)
        if npc_state["dead"]:
            return ActResult(f"{npc.name}已经倒下了。", state, "combat")

        weapon = weapon_by_name(weapon_name) if weapon_name else Weapon("徒手", "斗殴", "1d3")
        db_text, _build = damage_bonus(inv.attrs)
        db_value = roll(db_text, self.rng)[0] if "d" in db_text else int(db_text)

        outcome = resolve_attack(
            inv.skill_value(weapon.skill),
            weapon=weapon,
            defender_dodge=max(1, int(npc.stats.get("DEX", 50)) // 2),
            hp=npc_state["hp"],
            hp_max=npc_state["max"],
            damage_bonus=max(0, db_value),
            rng=self.rng,
        )
        npc_state["hp"] = max(0, outcome.hp_after)
        if npc_state["hp"] == 0:
            npc_state["dead"] = True

        counter = None
        if outcome.hit and not npc_state["dead"]:
            npc_skill = int((npc.stats.get("skills") or {}).get("斗殴", 25))
            counter = resolve_attack(
                npc_skill,
                hp=inv.hp,
                hp_max=inv.hp_max,
                defender_dodge=inv.skill_value("闪避"),
                rng=self.rng,
            )
            inv.state["hp"] = max(-99, counter.hp_after)
            self.store.update_character_state(char_id, inv.state)

        lines = [f"你{weapon.name}攻击{npc.name}：{outcome.summary()}"]
        if npc_state["dead"]:
            lines.append(f"{npc.name}倒下了。")
        elif counter is not None:
            lines.append(f"{npc.name}反击：{counter.summary()}")
        if inv.hp <= 0:
            lines.append("你倒下了。")

        self.store.append_roll(
            session_id, actor=str(qq), kind="combat", skill=weapon.skill,
            target=outcome.attack_check.target, difficulty="regular",
            d100_value=outcome.attack_check.roll, outcome=outcome.attack_check.outcome.value,
            detail={"npc": npc.id, "damage": outcome.damage, "npc_hp": npc_state["hp"]},
        )
        self.store.append_event(
            session_id, "combat_round", actor=str(qq),
            payload={
                "npc": npc.id, "hit": outcome.hit, "damage": outcome.damage,
                "npc_hp": npc_state["hp"], "player_hp": inv.hp,
            },
        )
        turn_no = int(session.get("turn_no") or 0) + 1
        self.store.update_session(session_id, turn_no=turn_no)
        self.store.update_session_state(session_id, state)

        narrative = await self.narrator.narrate({"kind": "combat", "text": "\n".join(lines)})
        return ActResult(narrative, state, "combat")

    async def sanity(self, session_id: int, qq: int, expression: str) -> ActResult:
        session = self.store.get_session(session_id)
        if session is None:
            return ActResult("这局不存在。", {}, "notice")
        state = self.store.get_session_state(session_id)
        campaign_id = int(session["campaign_id"])
        found = self.store.find_character_by_owner(campaign_id, int(qq))
        if found is None:
            return ActResult("你还没有调查员，先发 /coc 车卡。", state, "notice")
        char_id, inv = found

        total_before = int(state.get("san_loss_total", 0))
        result = sanity_check(
            inv.san, expression, self.rng, initial_san=inv.san_max, total_loss_before=total_before
        )
        inv.state["san"] = result.san_after
        state["san_loss_total"] = total_before + result.loss
        self.store.update_character_state(char_id, inv.state)

        lines = [result.summary()]
        if result.temp_insanity_check:
            symptom = roll_temporary_madness(self.rng)
            state["madness"] = symptom
            lines.append(f"你陷入了「{symptom['name']}」：{symptom['desc']}")
        if result.indefinite_insanity:
            chronic = roll_indefinite_madness(self.rng)
            state["madness_indefinite"] = chronic
            lines.append(f"长期影响：「{chronic['name']}」——{chronic['desc']}")

        self.store.append_roll(
            session_id, actor=str(qq), kind="san", skill="SAN",
            target=result.san_before, difficulty="regular",
            d100_value=result.roll, outcome="regular" if result.success else "failure",
            detail={"loss": result.loss, "san_after": result.san_after},
        )
        self.store.append_event(
            session_id, "san_check", actor=str(qq),
            payload={"expression": expression, "loss": result.loss, "san_after": result.san_after},
        )
        self.store.update_session_state(session_id, state)

        narrative = await self.narrator.narrate({"kind": "sanity", "text": "\n".join(lines)})
        return ActResult(narrative, state, "sanity", check=None)

    # ---------------- 视图与收尾 ----------------

    async def _enter_scene(self, session_id: int, module: Module, scene: Scene, state: dict) -> str:
        choices = []
        for clue in module.scene_clues(scene.id):
            choices.append(f"调查{clue.name}")
        for npc in module.scene_npcs(scene.id):
            choices.append(f"和{npc.name}说话")
        for exit_ in scene.exits:
            choices.append(f"去{exit_.label or module.scene(exit_.to).title}")
        return await self._narrate(
            session_id, module, scene, "scene", state=state, choices=choices[:6]
        )

    def scene_view(self, session_id: int) -> dict:
        session = self.store.get_session(session_id)
        if session is None:
            return {}
        module = self._module(int(session["campaign_id"]))
        state = self.store.get_session_state(session_id)
        scene = module.scene(state.get("scene") or module.first_scene)
        discovered = [
            {"id": c["clue_id"], "name": (module.clue(c["clue_id"]).name if module.clue(c["clue_id"]) else c["clue_id"])}
            for c in self.store.discovered_clues(session_id)
        ]
        exits = [
            {"to": e.to, "label": e.label or module.scene(e.to).title}
            for e in scene.exits
        ]
        return {
            "scene": {"id": scene.id, "title": scene.title, "player_text": scene.player_text},
            "clues": discovered,
            "exits": exits,
            "turn_no": int(session.get("turn_no") or 0),
            "tension": int(state.get("tension", 0)),
            "ended": state.get("ended"),
        }

    def _match_ending(self, module: Module, action: Action, state: dict, session_id: int):
        for ending in module.endings:
            condition = ending.get("condition") or {}
            if condition.get("clue") and not self.store.has_clue(session_id, condition["clue"]):
                continue
            if condition.get("action") and condition["action"] != action.type:
                continue
            if condition.get("scene") and condition["scene"] != state.get("scene"):
                continue
            return ending
        return None

    # ---------------- 匹配辅助 ----------------

    @staticmethod
    def _similar(target: str, name: str) -> bool:
        """宽松匹配：去掉口语虚词后，任一方包含另一方即算命中。"""
        if not target:
            return True  # 没说对象时取场景内第一个可交互物
        strip = "的那这个了张本封把向在里"
        a = "".join(ch for ch in target if ch not in strip)
        b = "".join(ch for ch in name if ch not in strip)
        if not a or not b:
            return False
        if a in b or b in a:
            return True
        # 退一步用二元组匹配：「地上的符号」↔「环状符号」共享「符号」
        if len(a) >= 2:
            return any(a[i:i + 2] in b for i in range(len(a) - 1))
        return False

    @classmethod
    def _match_clue(cls, module: Module, scene: Scene, target: str) -> Clue | None:
        for clue in module.scene_clues(scene.id):
            if cls._similar((target or "").strip(), clue.name):
                return clue
        return None

    @classmethod
    def _match_npc(cls, module: Module, scene: Scene, target: str) -> Npc | None:
        for npc in module.scene_npcs(scene.id):
            if cls._similar((target or "").strip(), npc.name):
                return npc
        return None

    @classmethod
    def _match_exit(cls, module: Module, scene: Scene, target: str):
        for exit_ in scene.exits:
            label = exit_.label or module.scene(exit_.to).title
            if cls._similar((target or "").strip(), label):
                return exit_
        return None
