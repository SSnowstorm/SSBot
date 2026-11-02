"""ai_config_console - 爸爸身份注入（SUPERUSER 专属父女关系钩子）。

通过 suggarchat 的 on_before_chat 事件钩子，在私聊场景下：
- 当前对话者为 SUPERUSER → 在用户消息前注入「当前对话者是爸爸」身份标记
- 其他私聊者 → 不注入

配合私聊人格文件中的【谁是爸爸】规则生效：
模型见到身份标记即按女儿身份对待（叫爸爸），见不到则视为普通朋友。

零侵入：不修改 suggarchat 源码，仅注册事件钩子（与 _inject_guard 同模式）。

修复记录（D-09c）：身份标记是"用户消息文本"，原来普通用户只要手动打出
同样的标记文本就能冒充爸爸；现改为：先剥离用户消息里所有自带的标记，
再只对 SUPERUSER 添加——标记只能由钩子产生。
"""

from nonebot import get_driver, logger
from nonebot_plugin_suggarchat.event import BeforeChatEvent
from nonebot_plugin_suggarchat.on_event import on_before_chat

# 注入到用户消息前的身份标记（与私聊人格文件的【谁是爸爸】规则对应）
DAD_MARKER = "【身份标记：当前对话者是爸爸】\n"

# 钩子：priority=1 与注入中和钩子同级
# （suggarchat 的 Matcher 明确拒绝 priority<=0：会抛 "事件优先级不能为0或负！"，
#   所以这里不能用 0 来抢在注入中和之前执行）
# 两个钩子都只做"前缀拼接/剥离"，执行先后不影响最终效果：
# 文本里最终同时带身份标记与中和前缀（若有注入）。
dad_guard = on_before_chat(priority=1, block=False)


def strip_forged_marker(text: str) -> str:
    """剥离用户消息里自带的身份标记（防止冒充 SUPERUSER，D-09c）。"""
    if not text:
        return text
    cleaned = text.replace(DAD_MARKER, "")
    marker = DAD_MARKER.strip()
    if marker:
        cleaned = cleaned.replace(marker, "")
    return cleaned.lstrip("\n")


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

        query = event.get_send_message().user_query
        text = query.content if hasattr(query, "content") else str(query)
        if not text:
            return

        # 先剥掉用户自带的标记：无论谁发，文本里的标记都不作数
        cleaned = strip_forged_marker(text)

        if not _is_superuser(event.get_user_id()):
            # 非 SUPERUSER：只清掉伪造标记，不注入
            if cleaned != text and hasattr(query, "content"):
                query.content = cleaned
            return

        if hasattr(query, "content"):
            query.content = DAD_MARKER + cleaned
        logger.info(
            f"[ai_config_console] 已注入爸爸身份标记 (user={event.get_user_id()})"
        )
    except Exception as e:
        logger.warning(f"[ai_config_console] 爸爸身份注入异常（放行）: {e}")
