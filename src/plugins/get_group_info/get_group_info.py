"""群信息查询。

命令（需 @机器人）：
    /get_list    查看当前群信息 + 成员概览

修复记录（D-06）：原实现把 group_id 硬编码成 527020285，把整个成员列表和群信息
打进 INFO 日志，最后只回复一个 "?"。现在按当前会话取群号、输出摘要，
完整数据仅 DEBUG 记录。
"""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.log import logger
from nonebot.rule import to_me

command = on_command(
    "get_list",
    aliases={"群成员", "成员列表"},
    rule=to_me(),
    priority=10,
    block=True,
)

# 概览里最多列出的成员数
MAX_MEMBERS_SHOWN = 10


def _member_name(member: dict) -> str:
    """优先群名片，其次昵称，最后 QQ 号。"""
    return (
        member.get("card")
        or member.get("nickname")
        or str(member.get("user_id", "?"))
    )


@command.handle()
async def get_group_list(bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await command.finish("该命令只能在群聊中使用。")

    group_id = event.group_id

    try:
        info = await bot.get_group_info(group_id=group_id, no_cache=True)
    except Exception as e:
        logger.warning(f"[get_group_info] 获取群信息失败 group={group_id}: {e}")
        info = {}

    try:
        members = await bot.get_group_member_list(group_id=group_id) or []
    except Exception as e:
        logger.error(f"[get_group_info] 获取群成员列表失败 group={group_id}: {e}")
        await command.finish(f"获取群成员列表失败：{e}")

    owner = info.get("owner") or {}
    owner_name = (
        owner.get("card")
        or owner.get("nickname")
        or (str(owner["user_id"]) if owner.get("user_id") else "未知")
    )
    admins = [m for m in members if m.get("role") == "admin"]

    lines = [
        f"【群信息】{info.get('group_name') or f'群 {group_id}'}",
        f"群号：{group_id}",
        f"成员：{len(members)} 人"
        + (f"（上限 {info['max_member_count']}）" if info.get("max_member_count") else ""),
        f"群主：{owner_name}",
        f"管理员：{len(admins)} 人",
    ]

    if members:
        lines.append("—— 成员概览 ——")
        for idx, member in enumerate(members[:MAX_MEMBERS_SHOWN], 1):
            role = {"owner": "群主", "admin": "管理"}.get(member.get("role"), "成员")
            lines.append(f"{idx}. {_member_name(member)}（{member.get('user_id')}·{role}）")
        if len(members) > MAX_MEMBERS_SHOWN:
            lines.append(f"…… 仅显示前 {MAX_MEMBERS_SHOWN} 位（共 {len(members)} 人）")

    logger.debug(f"[get_group_info] group={group_id} 成员数={len(members)}")
    await command.finish("\n".join(lines))
