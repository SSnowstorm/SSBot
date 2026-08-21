"""ai_config_console - 爸爸身份注入（SUPERUSER 专属父女关系钩子）。

通过 suggarchat 的 on_before_chat 事件钩子，在私聊场景下：
- 当前对话者为 SUPERUSER → 在用户消息前注入「当前对话者是爸爸」身份标记
- 其他私聊者 → 不注入

配合私聊人格文件中的【谁是爸爸】规则生效：
模型见到身份标记即按女儿身份对待（叫爸爸），见不到则视为普通朋友。

零侵入：不修改 suggarchat 源码，仅注册事件钩子（与 _inject_guard 同模式）。
"""

from nonebot import get_driver, logger
from nonebot_plugin_suggarchat.event import BeforeChatEvent
from nonebot_plugin_suggarchat.on_event import on_before_chat

# 注入到用户消息前的身份标记（与私聊人格文件的【谁是爸爸】规则对应）
DAD_MARKER = "【身份标记：当前对话者是爸爸】\n"

# 钩子（与注入守卫同优先级，block=False 不阻断流程）
dad_guard = on_before_chat(priority=1, block=False)


def _is_superuser(user_id: int) -> bool:
    """判断 user_id 是否为 NoneBot 配置的 SUPERUSER。"""
    superusers = {
        int(u) for u in get_driver().config.superusers if str(u).isdigit()
    }
    return user_id in superusers


@dad_guard.append_handler
async def inject_dad_marker(event: BeforeChatEvent) -> None:
    """私聊时向 SUPERUSER 注入「爸爸」身份标记。"""
    try:
        # 仅私聊场景
        if event.get_event_on_location() != "private":
            return
        # 仅 SUPERUSER
        if not _is_superuser(event.get_user_id()):
            return

        query = event.get_send_message().user_query
        text = query.content if hasattr(query, "content") else str(query)
        if not text:
            return
        # 已注入过则跳过（避免重复前缀）
        if text.startswith(DAD_MARKER):
            return

        if hasattr(query, "content"):
            query.content = DAD_MARKER + text
        logger.info(
            f"[ai_config_console] 已注入爸爸身份标记 (user={event.get_user_id()})"
        )
    except Exception as e:
        logger.warning(f"[ai_config_console] 爸爸身份注入异常（放行）: {e}")
