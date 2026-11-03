"""``/coc`` 命令层（P0 最小可用）。

P0 只做三件事：车卡、检定、查状态。真正的跑团流程（场景 / 回合 / 线索）
要到 P1，所以这里刻意保持薄：命令只做参数解析与渲染，规则全在 ``domain``。
"""

from __future__ import annotations

import os

from nonebot import get_driver, on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.log import logger
from nonebot.params import CommandArg

from .domain import (
    Difficulty,
    Investigator,
    damage_bonus,
    movement,
    random_investigator,
    resolve,
    validate,
)
from .store.db import DEFAULT_DB_PATH, CocStore

coc_cmd = on_command("coc", aliases={"跑团", "COC"}, priority=10, block=True)

_store: CocStore | None = None


def get_store() -> CocStore:
    """惰性单例：首次调用时才建库，避免 import 阶段写文件。"""
    global _store
    if _store is None:
        path = os.getenv("COC_DB_PATH") or DEFAULT_DB_PATH
        _store = CocStore(path)
        logger.info(f"[coc] 数据库就绪: {_store.path}")
    return _store


def _here(event: MessageEvent) -> int:
    """群聊用群号，私聊用负的用户号，保证一间一 campaign。"""
    group_id = getattr(event, "group_id", None)
    return int(group_id) if group_id else -int(event.user_id)


def _ensure_campaign(event: MessageEvent) -> int:
    store = get_store()
    scope = _here(event)
    campaign = store.find_campaign_by_group(scope)
    if campaign:
        return int(campaign["id"])
    return store.create_campaign(f"群 {scope} 的团", group_id=scope)


def format_sheet(inv: Investigator) -> str:
    skills = inv.effective_skills()
    key_skills = ["侦查", "聆听", "图书馆使用", "闪避", "斗殴", "心理学"]
    skill_line = "、".join(f"{name} {skills.get(name, 0)}" for name in key_skills if name in skills)
    db_text, build = damage_bonus(inv.attrs)
    return (
        f"【调查员】{inv.name}（{inv.occupation}）\n"
        f"STR {inv.attrs.get('STR')}  CON {inv.attrs.get('CON')}  SIZ {inv.attrs.get('SIZ')}  "
        f"DEX {inv.attrs.get('DEX')}\n"
        f"APP {inv.attrs.get('APP')}  INT {inv.attrs.get('INT')}  POW {inv.attrs.get('POW')}  "
        f"EDU {inv.attrs.get('EDU')}\n"
        f"HP {inv.hp}/{inv.hp_max}  MP {inv.mp}/{inv.mp_max}  SAN {inv.san}/{inv.san_max}  "
        f"幸运 {inv.luck}\n"
        f"MOV {movement(inv.attrs)}  伤害加值 {db_text}  体格 {build}\n"
        f"技能：{skill_line}"
    )


USAGE = (
    "【跑团 P0 命令】\n"
    "/coc 车卡 [名字]        随机生成一张调查员卡\n"
    "/coc 检定 <技能> [困难/极难]   掷一次技能检定\n"
    "/coc 状态               查看自己的角色卡\n"
    "\n提示：规则为 CoC 7e 基础规则，房规以开团公告为准。"
)


@coc_cmd.handle()
async def handle_coc(event: MessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    sub, _, rest = text.partition(" ")
    sub = sub.strip() or "帮助"

    if sub in ("车卡", "新建", "new"):
        await _handle_create(event, rest.strip())
        return
    if sub in ("检定", "check", "roll"):
        await _handle_check(event, rest.strip())
        return
    if sub in ("状态", "角色", "sheet", "卡"):
        await _handle_sheet(event)
        return

    await coc_cmd.finish(USAGE)


async def _handle_create(event: MessageEvent, name: str) -> None:
    store = get_store()
    campaign_id = _ensure_campaign(event)
    default_name = f"{event.sender.nickname if getattr(event, 'sender', None) else '调查员'}"
    inv = random_investigator(name=name or f"{default_name}的调查员")

    problems = validate(inv)
    if problems:
        await coc_cmd.finish("角色卡生成异常：" + "；".join(problems))

    char_id = store.save_character(campaign_id, inv, type_="pc", owner_qq=int(event.user_id))
    session = store.find_running_session(campaign_id)
    if session:
        store.append_event(
            int(session["id"]), "character_import",
            actor=str(event.user_id),
            payload={"character_id": char_id, "name": inv.name, "source": "random"},
        )

    await coc_cmd.finish(
        "已生成调查员（可继续 /coc 状态 查看）：\n" + format_sheet(inv)
    )


async def _handle_check(event: MessageEvent, rest: str) -> None:
    store = get_store()
    campaign_id = _ensure_campaign(event)
    found = store.find_character_by_owner(campaign_id, int(event.user_id))
    if found is None:
        await coc_cmd.finish("还没有角色卡，先发 /coc 车卡 生成一张。")

    _, inv = found
    parts = [p for p in rest.split() if p]
    if not parts:
        await coc_cmd.finish("用法：/coc 检定 <技能> [困难/极难]，例如 /coc 检定 侦查")
    skill_name = parts[0]
    difficulty = Difficulty.REGULAR
    if len(parts) > 1:
        try:
            difficulty = Difficulty.parse(parts[1])
        except ValueError:
            await coc_cmd.finish(f"不认识的难度：{parts[1]}（可用 困难 / 极难）")

    skill_value = inv.skill_value(skill_name)
    result = resolve(skill_name, skill_value, difficulty)

    session = store.find_running_session(campaign_id)
    if session:
        store.append_roll(
            int(session["id"]),
            actor=str(event.user_id),
            kind="check",
            skill=skill_name,
            target=result.target,
            difficulty=result.difficulty.value,
            bonus_penalty=result.bonus - result.penalty,
            d100_value=result.roll,
            outcome=result.outcome.value,
            detail=result.detail,
        )

    await coc_cmd.finish(f"🎲 {result.summary()}")


async def _handle_sheet(event: MessageEvent) -> None:
    store = get_store()
    campaign_id = _ensure_campaign(event)
    found = store.find_character_by_owner(campaign_id, int(event.user_id))
    if found is None:
        await coc_cmd.finish("还没有角色卡，先发 /coc 车卡 生成一张。")
    _, inv = found
    await coc_cmd.finish(format_sheet(inv))


__all__ = ["coc_cmd", "get_store", "format_sheet"]
