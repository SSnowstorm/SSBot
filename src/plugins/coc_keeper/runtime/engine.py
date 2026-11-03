"""场景状态机 + 行动结算（P1）。

一次 ``act`` 的流程：
    解析动作 → 合法性 → 检定（可选）→ 状态变更 → 线索/场景/结局 → 事实包 → 叙事

状态只落在两处：``session.state_json``（场景/张紧度/是否结束）与 ``clue_state`` 表（已发现线索）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from nonebot.log import logger

from ..domain import Difficulty, Investigator, resolve
from ..module.model import Clue, Module, Npc, Scene, module_from_row
from .actions import Action, parse_action
from .narrator import Narrator, TemplateNarrator


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

    def __init__(self, store, narrator: Narrator | None = None, rng: random.Random | None = None):
        self.store = store
        self.narrator = narrator or TemplateNarrator()
        self.rng = rng or random.Random()

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

        narrative = await self._enter_scene(scene, module)
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

        action = parse_action(
            text,
            clues=[c.name for c in module.scene_clues(scene.id) if not self.store.has_clue(session_id, c.id)],
            npcs=[n.name for n in module.scene_npcs(scene.id)],
            exits=[e.label or module.scene(e.to).title for e in scene.exits],
        )

        result = await self._dispatch(session_id, module, scene, inv, action, state, qq)
        result = await self._after_action(session_id, module, scene, result)

        # 回合推进 + 记录
        turn_no = int(session.get("turn_no") or 0) + 1
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
            result.narrative = await self.narrator.narrate(
                {"kind": "ending", "text": ending.get("text") or "", "ending_id": ending.get("id")}
            )
            result.ended = True
            result.kind = "ending"

        return result

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
        if kind == "move":
            return await self._move(session_id, module, scene, action, state, qq)
        if kind in ("use_item", "attack", "dodge", "skill_check", "wait"):
            return await self._simple(session_id, module, scene, inv, action, state, qq)

        return ActResult(
            narrative=await self.narrator.narrate(
                {"kind": "clarify", "text": "我没太听明白。你是想搜查、问人，还是去别的地方？"}
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
            return await self._discover(session_id, clue, state, action, qq, check=None)

        difficulty = Difficulty.parse(condition.get("difficulty", "regular"))
        check = resolve(skill_name, inv.skill_value(skill_name), difficulty, rng=self.rng)
        self.store.append_roll(
            session_id, actor=str(qq), kind="check", skill=skill_name,
            target=check.target, difficulty=check.difficulty.value,
            bonus_penalty=check.bonus - check.penalty,
            d100_value=check.roll, outcome=check.outcome.value, detail=check.detail,
        )
        if check.success:
            return await self._discover(session_id, clue, state, action, qq, check=check)

        narrative = await self.narrator.narrate(
            {"kind": "check_fail", "check": {"skill": skill_name, "roll": check.roll, "target": check.target}}
        )
        return ActResult(narrative, state, "investigate", action, check=check)

    async def _discover(self, session_id, clue: Clue, state, action, qq, *, check) -> ActResult:
        self.store.discover_clue(session_id, clue.id, by=str(qq), scene_id=clue.scene)
        self.store.append_event(
            session_id, "clue_found", actor=str(qq), payload={"clue": clue.id, "scene": clue.scene}
        )
        # 线索可能提升张力（关键线索给压力）
        state["tension"] = min(100, int(state.get("tension", 0)) + (10 if clue.importance == "main" else 5))
        narrative = await self.narrator.narrate(
            {"kind": "clue", "clue": {"name": clue.name, "player_text": clue.player_text}}
        )
        return ActResult(narrative, state, "clue", action, check=check, clue=clue.id)

    async def _talk(self, session_id, module, scene, action, state, qq) -> ActResult:
        npc = self._match_npc(module, scene, action.target)
        if npc is None:
            return ActResult("这里没有可以搭话的人。", state, "talk", action)

        line = str(npc.public.get("attitude") or "看了你一眼")
        extra = ""
        if npc.gives_clue and not self.store.has_clue(session_id, npc.gives_clue):
            clue = module.clue(npc.gives_clue)
            if clue is not None:
                self.store.discover_clue(session_id, clue.id, by=str(qq), scene_id=clue.scene)
                self.store.append_event(
                    session_id, "clue_found", actor=str(qq), payload={"clue": clue.id, "via": npc.id}
                )
                extra = clue.player_text
                line = f"【{npc.name}】{npc.public.get('voice') or ''}".strip()

        text = (line + ("\n" + extra if extra else "")).strip()
        narrative = await self.narrator.narrate(
            {"kind": "npc", "npc": {"name": npc.name, "line": text}, "clue_text": extra}
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
                await self.narrator.narrate({"kind": "blocked", "text": f"这条路现在还走不通。{hint}"}),
                state, "move", action,
            )

        target_scene = module.scene(exit_.to)
        state["scene"] = target_scene.id
        state.setdefault("visited", []).append(target_scene.id)
        self.store.update_session(session_id, scene=target_scene.id)
        self.store.append_event(
            session_id, "scene_enter", actor=str(qq), payload={"scene": target_scene.id}
        )
        narrative = await self._enter_scene(target_scene, module)
        return ActResult(narrative, state, "scene", action)

    async def _simple(self, session_id, module, scene, inv, action, state, qq) -> ActResult:
        if action.type == "wait":
            state["tension"] = min(100, int(state.get("tension", 0)) + 5)
            return ActResult(
                await self.narrator.narrate({"kind": "wait", "text": "你们在原地等了一会儿，雾更浓了。"}),
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

        if idle >= 3 and not state.get(f"hint_{scene.id}"):
            hint = self._soft_hint(module, scene, session_id)
            if hint:
                state[f"hint_{scene.id}"] = True
                state["tension"] = min(100, int(state.get("tension", 0)) + 5)
                self.store.append_event(
                    session_id, "keeper_mercy", actor="system",
                    payload={"reason": "soft_hint", "scene": scene.id},
                )
                result.narrative = f"{result.narrative}\n\n（KP 提示）{hint}"
                return result

        if idle >= 6 and not state.get(f"tick_{scene.id}"):
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

    # ---------------- 视图与收尾 ----------------

    async def _enter_scene(self, scene: Scene, module: Module) -> str:
        choices = []
        for clue in module.scene_clues(scene.id):
            choices.append(f"调查{clue.name}")
        for npc in module.scene_npcs(scene.id):
            choices.append(f"和{npc.name}说话")
        for exit_ in scene.exits:
            choices.append(f"去{exit_.label or module.scene(exit_.to).title}")
        return await self.narrator.narrate(
            {
                "kind": "scene",
                "scene": {"id": scene.id, "title": scene.title, "player_text": scene.player_text},
                "choices": choices[:6],
            }
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
