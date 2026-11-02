"""我是谁：回显发送者身份。

修复记录（D-06 附带）：
- 原实现 `bot.get_group_info()` 缺 group_id 且没有 await，调用必抛异常；
- `"[CQ:at,qq={}]".format(id)` 把内置函数 id 当 QQ 号拼进 CQ 码，发送必失败；
- 命令名 `"say my name"` 含空格，NoneBot 按首个空白切分命令名，实际永远匹配不上。

现改为 whoami（中文别名 我是谁 / say_my_name），用 MessageSegment 拼 at，不再手写 CQ 码。
"""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment

command = on_command(
    "whoami",
    aliases={"我是谁", "say_my_name"},
    priority=10,
    block=True,
)


@command.handle()
async def whoami(event: MessageEvent):
    sender = getattr(event, "sender", None)
    nickname = getattr(sender, "card", None) or getattr(sender, "nickname", None) or "未知"

    text = f"你是 {nickname}（QQ: {event.user_id}）"
    group_id = getattr(event, "group_id", None)
    if group_id:
        text += f"，当前群：{group_id}"

    await command.finish(MessageSegment.at(event.user_id) + " " + text)
