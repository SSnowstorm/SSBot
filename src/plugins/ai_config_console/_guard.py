"""ai_config_console - 私聊人格设置权限守卫。

需求：私聊中设置人格（/prompt 命令）也需 admin 以上权限。
实现：NoneBot2 run_preprocessor 钩子（零侵入，不改 suggarchat 源码）。

判定逻辑：
- 私聊 + 非管理员 + 消息是 /prompt 命令 → 拦截并提示
- 群聊保持 suggarchat 原逻辑（群主/群管/管理员可用）
- 管理员 = SUPERUSERS ∪ suggarchat [admin].admins

修复记录（D-09a）：原来用 str.startswith(("/prompt", "prompt")) 判定，
"promptly 你好" 之类普通消息会被误拦；改为词边界正则。
"""

import re
import time

from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.exception import IgnoredException
from nonebot.message import run_preprocessor

from ._config_store import _load_toml

# /prompt 命令判定：允许斜杠（含全角）或裸命令，但命令名后必须是空白或结尾
# 例："/prompt --(set) 你是猫娘" 命中；"promptly 你好" 不命中
_PROMPT_CMD_RE = re.compile(r"^[/／]?prompt(?=\s|$)", re.IGNORECASE)


def is_prompt_command(text: str) -> bool:
    """判断消息是否为 /prompt 命令（词边界匹配，避免前缀误拦）。"""
    return bool(_PROMPT_CMD_RE.match((text or "").strip()))


# D-13：run_preprocessor 会对"每个命中的 matcher"各执行一次，同一条消息可能被拦截多次，
# 导致拦截提示重复刷屏。这里按 (self_id, user_id, message_id) 去重，只提醒一次。
_BLOCKED_TTL = 60.0
_MAX_BLOCKED = 500
_blocked: dict[tuple[str, str, int, int], float] = {}


def _already_blocked(event: MessageEvent) -> bool:
    """同一条消息是否已经提示过（标记并返回 False 表示首次）。"""
    # 带上事件时间：message_id 在个别协议端/测试场景下可能重复，时间戳能把两者区分开
    key = (
        str(getattr(event, "self_id", "")),
        event.get_user_id(),
        int(getattr(event, "message_id", 0) or 0),
        int(getattr(event, "time", 0) or 0),
    )
    now = time.time()
    if len(_blocked) > _MAX_BLOCKED:
        for k, ts in list(_blocked.items()):
            if now - ts > _BLOCKED_TTL:
                _blocked.pop(k, None)
    if key in _blocked:
        return True
    _blocked[key] = now
    return False


def _is_admin(user_id: str) -> bool:
    """判断用户是否为管理员：SUPERUSERS ∪ suggarchat [admin].admins。"""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False

    # SUPERUSERS（.env）
    config = get_driver().config
    if uid in {int(s) for s in getattr(config, "superusers", set()) if s.isdigit()}:
        return True

    # suggarchat [admin].admins（config.toml）
    try:
        data = _load_toml()
        admins = set(data.get("admin", {}).get("admins", []))
        if uid in admins:
            return True
    except Exception:
        pass
    return False


@run_preprocessor
async def _guard_prompt_in_private(bot: Bot, event: MessageEvent) -> None:
    """私聊非管理员拦截 /prompt 命令。"""
    # 仅处理私聊
    if isinstance(event, GroupMessageEvent):
        return

    # 仅拦截 /prompt 命令
    if not is_prompt_command(event.get_plaintext()):
        return

    # 管理员放行
    if _is_admin(event.get_user_id()):
        return

    # 拦截：发送提示（同一条消息只提示一次）+ 阻止后续处理
    if not _already_blocked(event):
        await bot.send(event, "私聊中设置人格需要管理员权限（/choose_prompt 仅管理员可用）。")
    raise IgnoredException("非管理员私聊 /prompt 已拦截")
