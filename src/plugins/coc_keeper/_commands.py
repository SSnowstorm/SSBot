"""``/coc`` 命令层（P1）。

P0：车卡 / 检定 / 状态
P1：开团 / 行动 / 场景 / 线索 / 结束 —— 接场景状态机与模板或 LLM 叙事。

命令只做参数解析与渲染；规则、状态、叙事分别在 domain / runtime / narrator。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from nonebot import get_driver, on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
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
from .module import Module, ModuleError, load_module
from .replay import build_replay, save_replay
from .runtime import CocRuntime, build_narrator
from .runtime.persona import load_persona
from .store.db import DEFAULT_DB_PATH, CocStore

MODULE_DIR = Path(__file__).parent / "data" / "modules"
REPLAY_DIR = Path(DEFAULT_DB_PATH).parent / "replays"

coc_cmd = on_command("coc", aliases={"跑团", "COC"}, priority=10, block=True)

_store: CocStore | None = None
_runtime: CocRuntime | None = None


def get_store() -> CocStore:
    """惰性单例：首次调用时才建库，避免 import 阶段写文件。"""
    global _store
    if _store is None:
        path = os.getenv("COC_DB_PATH") or DEFAULT_DB_PATH
        _store = CocStore(path)
        logger.info(f"[coc] 数据库就绪: {_store.path}")
    return _store


def get_runtime() -> CocRuntime:
    """惰性单例：按环境变量决定「规则兜底」还是「模型理解 + 模型台词」。"""
    global _runtime
    if _runtime is None:
        from .runtime.llm import (
            LlmClient,
            LlmDialogueWriter,
            LlmIntentParser,
            RuleIntentParser,
            TemplateDialogueWriter,
        )

        enabled = os.getenv("COC_LLM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        client = LlmClient()
        if enabled:
            intent_parser = LlmIntentParser(client, RuleIntentParser())
            dialogue = LlmDialogueWriter(client, TemplateDialogueWriter())
            logger.info(f"[coc] 意图/台词: LLM({client.model}) 可用={client.available}")
        else:
            intent_parser = RuleIntentParser()
            dialogue = TemplateDialogueWriter()
            logger.info("[coc] 意图/台词: 规则模式（COC_LLM_ENABLED 未开启）")
        _runtime = CocRuntime(
            get_store(),
            build_narrator(),
            intent_parser=intent_parser,
            dialogue=dialogue,
            summarizer=client if enabled else None,
            persona_loader=lambda scene: load_persona(scene),
        )
    return _runtime


# ---------------- 作用域 / 权限 ----------------

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


def _is_admin(event: MessageEvent) -> bool:
    try:
        superusers = {str(u) for u in get_driver().config.superusers}
    except Exception:
        superusers = set()
    if str(event.user_id) in superusers:
        return True
    sender = getattr(event, "sender", None)
    return getattr(sender, "role", "") in ("owner", "admin")


# ---------------- 模组 ----------------

def list_builtin_modules() -> list[str]:
    return sorted(path.stem for path in MODULE_DIR.glob("*.json"))


def load_builtin_module(name: str) -> Module:
    """按文件名或模组标题加载内置模组。"""
    name = (name or "").strip() or "wugang"
    path = MODULE_DIR / f"{name}.json"
    if path.is_file():
        return load_module(path)
    for candidate in MODULE_DIR.glob("*.json"):
        module = load_module(candidate)
        if module.title == name:
            return module
    raise FileNotFoundError(f"未找到模组: {name}")


def ensure_module(name: str) -> int:
    """确保模组已入库，返回 module_id。"""
    store = get_store()
    name = (name or "").strip()
    row = store.find_module_by_title(name) if name else None
    if row:
        return int(row["id"])
    module = load_builtin_module(name)
    existing = store.find_module_by_title(module.title)
    if existing:
        return int(existing["id"])
    return store.save_module(module)


# ---------------- 渲染 ----------------

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
    "【跑团命令】\n"
    "  /coc 开团 [模组]      开局（管理员）\n"
    "  /coc 车卡 [名字]      随机生成调查员\n"
    "  /coc 行动 <做什么>    在当前场景行动\n"
    "  /coc 场景             查看当前场景与出口\n"
    "  /coc 线索             查看已发现线索\n"
    "  /coc 检定 <技能> [困难/极难]\n"
    "  /coc 状态             查看角色卡\n"
    "  /coc 攻击 <目标> [武器]  攻击场景里的 NPC\n"
    "  /coc 理智 <损失>     理智检定，如 /coc 理智 1/1d6\n"
    "  /coc 复盘 [文件]      生成本局战报（加「文件」上传群文件）\n"
    "  /coc 结束             结束本局（管理员）\n"
    "\n有进行中的团时，直接说话就是行动；想聊规则用 ooc: 或 // 开头。"
    "\n规则：CoC 7e 基础规则，房规以开团公告为准。"
)


# ---------------- 输出安全 ----------------

# 群聊里绝不该出现本地路径：盘符、UNC、常见用户目录
_PATH_STOP = r"[^\s，。；、！？：（）()\[\]<>]*"
_PATH_PATTERNS = (
    re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]" + _PATH_STOP),
    re.compile(r"\\\\" + _PATH_STOP),
    re.compile(r"(?:file://)?(?:/home|/Users|/root|/workspace|/tmp|/mnt)/" + _PATH_STOP),
)


def sanitize_public(text: str) -> str:
    """抹掉回复里的本地路径（防御性兜底：正常路径应只回文件名）。"""
    if not text:
        return text
    cleaned = text
    for pattern in _PATH_PATTERNS:
        cleaned = pattern.sub("（本地文件）", cleaned)
    return cleaned


def format_replay_reply(head: str, path: Path, *, uploaded: bool = False) -> str:
    """复盘回复只暴露文件名，不暴露目录。"""
    action = "已上传" if uploaded else "已生成"
    return f"{head}\n\n（完整战报{action}：{path.name}）"


async def _finish(text: str) -> None:
    """所有对外回复的唯一出口：统一脱敏后再发送。"""
    await coc_cmd.finish(sanitize_public(text))


# ---------------- 免命令模式 ----------------

_AMBIENT_OOC_PREFIXES = ("ooc:", "ooc：", "//", "【ooc】", "[ooc]", "（", "(",)
_AMBIENT_ON = {"1", "true", "yes", "on"}


def ambient_enabled() -> bool:
    return os.getenv("COC_AMBIENT", "true").strip().lower() in _AMBIENT_ON


def classify_ambient(text: str) -> tuple[str, str]:
    """把群消息分成 command / ooc / action / ignore。

    - 以 / 或 ！开头：命令，交给 /coc 处理
    - ooc: / // / （）包裹：OOC
    - 其余非空消息：当行动
    """
    raw = (text or "").strip()
    if not raw:
        return "ignore", ""
    lowered = raw.lower()
    # OOC 前缀优先：'//' 既是注释也是 OOC 标记，不能当命令
    for prefix in _AMBIENT_OOC_PREFIXES:
        if lowered.startswith(prefix.lower()):
            body = raw[len(prefix):].strip(" ）)")
            return "ooc", body or raw
    if raw.startswith(("/", "／", "!")):
        return "command", raw
    if len(raw) <= 1:
        return "ignore", raw
    return "action", raw


ambient_msg = on_message(priority=50, block=True)


@ambient_msg.handle()
async def handle_ambient(event: MessageEvent):
    """有进行中的团时，玩家直接说话就是行动；OOC 前缀不进叙事。"""
    if not ambient_enabled():
        return
    if str(event.user_id) == str(event.self_id):
        return

    kind, body = classify_ambient(event.get_plaintext())
    if kind in ("ignore", "command"):
        return

    store = get_store()
    campaign = store.find_campaign_by_group(_here(event))
    if not campaign:
        return
    campaign_id = int(campaign["id"])
    session = store.find_running_session(campaign_id)
    if not session:
        return
    if store.find_character_by_owner(campaign_id, int(event.user_id)) is None:
        return  # 只有本团玩家说话才算行动

    session_id = int(session["id"])
    if kind == "ooc":
        store.append_event(session_id, "ooc", actor=str(event.user_id), payload={"text": body[:200]})
        await ambient_msg.finish("（记下了，这条按 OOC 处理）")
        return

    result = await get_runtime().act(session_id, int(event.user_id), body)
    prefix = f"🎲 {result.check.summary()}\n" if result.check is not None else ""
    await ambient_msg.finish(sanitize_public(prefix + result.narrative))


# ---------------- 入口 ----------------

@coc_cmd.handle()
async def handle_coc(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
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
    if sub in ("开团", "开始", "start"):
        await _handle_start(event, rest.strip())
        return
    if sub in ("行动", "act", "做"):
        await _handle_act(event, rest.strip())
        return
    if sub in ("场景", "scene", "看"):
        await _handle_scene(event)
        return
    if sub in ("线索", "clue"):
        await _handle_clues(event)
        return
    if sub in ("攻击", "attack"):
        await _handle_attack(event, rest.strip())
        return
    if sub in ("理智", "san", "sc"):
        await _handle_sanity(event, rest.strip())
        return
    if sub in ("复盘", "replay", "战报"):
        await _handle_replay(bot, event, rest.strip())
        return
    if sub in ("结束", "stop"):
        await _handle_stop(event)
        return

    await _finish(USAGE)


# ---------------- P0 命令 ----------------

async def _handle_create(event: MessageEvent, name: str) -> None:
    store = get_store()
    campaign_id = _ensure_campaign(event)
    default_name = f"{event.sender.nickname if getattr(event, 'sender', None) else '调查员'}"
    inv = random_investigator(name=name or f"{default_name}的调查员")

    problems = validate(inv)
    if problems:
        await _finish("角色卡生成异常：" + "；".join(problems))

    char_id = store.save_character(campaign_id, inv, type_="pc", owner_qq=int(event.user_id))
    session = store.find_running_session(campaign_id)
    if session:
        store.append_event(
            int(session["id"]), "character_import",
            actor=str(event.user_id),
            payload={"character_id": char_id, "name": inv.name, "source": "random"},
        )

    await _finish("已生成调查员（可继续 /coc 状态 查看）：\n" + format_sheet(inv))


async def _handle_check(event: MessageEvent, rest: str) -> None:
    store = get_store()
    campaign_id = _ensure_campaign(event)
    found = store.find_character_by_owner(campaign_id, int(event.user_id))
    if found is None:
        await _finish("还没有角色卡，先发 /coc 车卡 生成一张。")

    _, inv = found
    parts = [p for p in rest.split() if p]
    if not parts:
        await _finish("用法：/coc 检定 <技能> [困难/极难]，例如 /coc 检定 侦查")
    skill_name = parts[0]
    difficulty = Difficulty.REGULAR
    if len(parts) > 1:
        try:
            difficulty = Difficulty.parse(parts[1])
        except ValueError:
            await _finish(f"不认识的难度：{parts[1]}（可用 困难 / 极难）")

    result = resolve(skill_name, inv.skill_value(skill_name), difficulty)
    session = store.find_running_session(campaign_id)
    if session:
        store.append_roll(
            int(session["id"]), actor=str(event.user_id), kind="check",
            skill=skill_name, target=result.target, difficulty=result.difficulty.value,
            bonus_penalty=result.bonus - result.penalty,
            d100_value=result.roll, outcome=result.outcome.value, detail=result.detail,
        )
    await _finish(f"🎲 {result.summary()}")


async def _handle_sheet(event: MessageEvent) -> None:
    store = get_store()
    campaign_id = _ensure_campaign(event)
    found = store.find_character_by_owner(campaign_id, int(event.user_id))
    if found is None:
        await _finish("还没有角色卡，先发 /coc 车卡 生成一张。")
    await _finish(format_sheet(found[1]))


# ---------------- P1 命令 ----------------

async def _handle_start(event: MessageEvent, name: str) -> None:
    if not _is_admin(event):
        await _finish("开团需要群管理员或超级用户。")

    store = get_store()
    campaign_id = _ensure_campaign(event)
    if store.find_running_session(campaign_id):
        await _finish("这个群已经有一局在跑，先 /coc 结束 再开新的。")

    try:
        module_id = ensure_module(name)
    except FileNotFoundError:
        await _finish(f"没找到模组「{name or 'wugang'}」。可用：{'、'.join(list_builtin_modules())}")
        return
    except ModuleError as exc:
        await _finish(f"模组校验失败：{exc}")
        return

    result = await get_runtime().start(campaign_id, module_id)
    module_row = store.get_module(module_id) or {}
    title = module_row.get("title") or "未知模组"
    await _finish(f"【开团】{title}\n\n{result.narrative}")


async def _handle_act(event: MessageEvent, text: str) -> None:
    store = get_store()
    campaign_id = _ensure_campaign(event)
    session = store.find_running_session(campaign_id)
    if not session:
        await _finish("这个群还没有进行中的团，先让管理员 /coc 开团。")
    if not text:
        await _finish("用法：/coc 行动 我想检查桌上那封信")

    result = await get_runtime().act(int(session["id"]), int(event.user_id), text)
    prefix = f"🎲 {result.check.summary()}\n" if result.check is not None else ""
    await _finish(prefix + result.narrative)


async def _handle_scene(event: MessageEvent) -> None:
    store = get_store()
    campaign_id = _ensure_campaign(event)
    session = store.find_running_session(campaign_id)
    if not session:
        await _finish("这个群还没有进行中的团。")

    view = get_runtime().scene_view(int(session["id"]))
    if not view:
        await _finish("读取场景失败。")
    scene = view["scene"]
    clues = "、".join(c["name"] for c in view["clues"]) or "（还没有）"
    exits = "、".join(e["label"] for e in view["exits"]) or "（无）"
    await _finish(
        f"【场景】{scene['title']}（第 {view['turn_no']} 回合｜张力 {view['tension']}）\n"
        f"{scene['player_text']}\n"
        f"已发现线索：{clues}\n"
        f"可去：{exits}"
    )


async def _handle_clues(event: MessageEvent) -> None:
    store = get_store()
    campaign_id = _ensure_campaign(event)
    session = store.find_running_session(campaign_id)
    if not session:
        await _finish("这个群还没有进行中的团。")

    view = get_runtime().scene_view(int(session["id"]))
    clues = view.get("clues") or []
    if not clues:
        await _finish("目前还没有发现任何线索。")
    await _finish("已发现线索：\n" + "\n".join(f"· {c['name']}" for c in clues))


async def _handle_attack(event: MessageEvent, rest: str) -> None:
    store = get_store()
    campaign_id = _ensure_campaign(event)
    session = store.find_running_session(campaign_id)
    if not session:
        await _finish("这个群还没有进行中的团。")

    parts = [p for p in rest.split() if p]
    if not parts:
        await _finish("用法：/coc 攻击 <目标> [武器]，例如 /coc 攻击 老陈 小刀")

    target = parts[0]
    weapon = parts[1] if len(parts) > 1 else ""
    result = await get_runtime().attack(int(session["id"]), int(event.user_id), target, weapon)
    await _finish(result.narrative)


async def _handle_sanity(event: MessageEvent, rest: str) -> None:
    store = get_store()
    campaign_id = _ensure_campaign(event)
    session = store.find_running_session(campaign_id)
    if not session:
        await _finish("这个群还没有进行中的团。")
    if not rest:
        await _finish("用法：/coc 理智 1/1d6（成功损失/失败损失）")

    result = await get_runtime().sanity(int(session["id"]), int(event.user_id), rest.strip())
    await _finish(result.narrative)


async def _handle_replay(bot: Bot, event: MessageEvent, arg: str) -> None:
    store = get_store()
    campaign_id = _ensure_campaign(event)
    session = store.find_running_session(campaign_id) or store.latest_session(campaign_id)
    if not session:
        await _finish("这个群还没有可复盘的局。")

    report = build_replay(store, int(session["id"]))
    path = save_replay(report, REPLAY_DIR)
    head = "\n".join(report.markdown.splitlines()[:10])

    group_id = getattr(event, "group_id", None)
    if "文件" in arg and group_id:
        try:
            await bot.upload_group_file(group_id=group_id, file=str(path), name=path.name)
            await _finish(format_replay_reply(head, path, uploaded=True))
        except Exception as exc:
            logger.warning(f"[coc] 战报上传失败: {exc!r}")
            await _finish(f"{head}\n\n（上传失败，完整战报已保存在服务器上）")
        return
    await _finish(format_replay_reply(head, path, uploaded=False))


async def _handle_stop(event: MessageEvent) -> None:
    if not _is_admin(event):
        await _finish("结束本局需要群管理员或超级用户。")

    store = get_store()
    campaign_id = _ensure_campaign(event)
    session = store.find_running_session(campaign_id)
    if not session:
        await _finish("当前没有进行中的团。")

    session_id = int(session["id"])
    state = store.get_session_state(session_id)
    state["ended"] = state.get("ended") or "manual"
    store.update_session_state(session_id, state)
    store.end_session(session_id)
    store.append_event(session_id, "session_end", actor=str(event.user_id), payload={"ending": state["ended"]})
    await _finish("本局已结束。可以用 /coc 线索 回顾已发现的线索。")


__all__ = [
    "coc_cmd", "get_store", "get_runtime", "format_sheet",
    "list_builtin_modules", "load_builtin_module", "ensure_module",
]