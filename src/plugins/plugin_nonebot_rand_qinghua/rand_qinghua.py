import json

from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.rule import to_me
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.typing import T_State
import nonebot
import requests

catch_cmd = on_command(cmd="情话", rule=to_me(), priority=10)


# [message.private.friend]: Message 1143302428 from 2232117623 '/情话'

@catch_cmd.handle()
async def rand_qinghua(bot: Bot, event: Event, state: T_State):
    get_msg = str(event.get_message())
    nonebot.log.logger.info(get_msg)
    id = event.get_user_id()
    msg = await get_qinghua()
    msg = "[CQ:at,qq={}]".format(id) + " " + str(msg)
    await catch_cmd.finish(Message(f"{msg}"))
    pass


async def get_qinghua():
    res = requests.get(
        url="https://api.uomg.com/api/rand.qinghua?format=json"
    )
    res_json = json.loads(res.text)
    key = res_json["code"]
    if key == 1:
        return res_json["content"]
    else:
        return res_json["msg"]


if __name__ == "__main__":
    # header =
    # res = requests.get(
    #     url="https://api.uomg.com/api/rand.qinghua?format=json"
    # )
    # if res.text["code"] == 1:
    #     print(res.text["content"])
    # else:
    #     print(res.text["code"])
    pass
