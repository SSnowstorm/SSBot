import json
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.rule import to_me
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.typing import T_State
import nonebot
import requests

command = on_command(cmd="say my name", rule=to_me(), priority=10)


@command.handle()
async def get_group_list(bot: Bot, event: Event, state: T_State):
    info = bot.get_group_info()
    session = event.get_session_id()
    nonebot.log.logger.info(f"Group_info is : {info}")
    nonebot.log.logger.info(f"Session_id is :{session}")
    name = event.get_user_id()
    msg = "[CQ:at,qq={}]".format(id) + str(name)
    await command.finish(Message(f"{msg}"))
