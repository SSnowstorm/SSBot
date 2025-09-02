import json
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.rule import to_me
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.typing import T_State
import nonebot
import requests

catch_cmd = on_command(cmd="井字棋", rule=to_me(), priority=10, )


@catch_cmd.handle()
async def game_start():
    msg = ""
    for row in 3:
        " | ".join(row)

if __name__ == "__main__":
    pass