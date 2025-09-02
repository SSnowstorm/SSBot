import json
from nonebot.adapters.onebot.v11 import Message, MessageSegment, GroupMessageEvent
from nonebot.rule import to_me, is_type
from nonebot import on_command, on_message, on_keyword
from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent
from nonebot.typing import T_State
import nonebot
import requests

command = on_command(cmd="get_list", rule=to_me(), priority=10)


# message = on_message(rule=to_me(),priority=10,handlers=command.handlers)

@command.handle()
async def get_group_list(bot: Bot, event: Event, state: T_State):
    desc = event.get_event_description()
    type = event.get_type()
    group_member_list = await bot.get_group_member_list(group_id=527020285)
    # info = event.get_group_info()
    group_info = await bot.get_group_info(group_id=527020285)
    # if event.get_type() is is_type(GroupMessageEvent):
    #     event = GroupMessageEvent()
    session = event.get_message()
    # if event.is_group
    nonebot.log.logger.info(f"desc is :{desc}")
    nonebot.log.logger.info(f"group_member_list is :{group_member_list}")
    nonebot.log.logger.info(f"group_info is : {group_info}")
    nonebot.log.logger.info(f"type is :{type}")
    nonebot.log.logger.info(f"Session_id is :{session}")
    await command.finish("?")

# @message.handle()
# async def handle_message(bot: Bot, event: MessageEvent, state: T_State):
#     if event.sender.
