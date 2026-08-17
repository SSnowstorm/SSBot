"""ai_config_console - 私聊人格设置权限守卫。

需求：私聊中设置人格（/prompt 命令）也需 admin 以上权限。
实现：NoneBot2 run_preprocessor 钩子（零侵入，不改 suggarchat 源码）。

判定逻辑：
- 私聊 + 非管理员 + 消息以 /prompt 开头 → 拦截并提示
- 群聊保持 suggarchat 原逻辑（群主/群管/管理员可用）
- 管理员 = SUPERUSERS ∪ suggarchat [admin].admins
"""

from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.exception import IgnoredException
from nonebot.message import run_preprocessor

from ._config_store import _load_toml

# /prompt 命令前缀（含不带斜杠的形式）
_PROMPT_PREFIXES = ("/prompt", "prompt")


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
    text = event.get_plaintext().strip()
    if not text.startswith(_PROMPT_PREFIXES):
        return

    # 管理员放行
    if _is_admin(event.get_user_id()):
        return

    # 拦截：发送提示 + 阻止后续处理
    await bot.send(event, "私聊中设置人格需要管理员权限（/choose_prompt 仅管理员可用）。")
    raise IgnoredException("非管理员私聊 /prompt 已拦截")
