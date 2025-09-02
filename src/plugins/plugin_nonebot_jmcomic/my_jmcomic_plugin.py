import asyncio
import os
import jmcomic
import nonebot
from nonebot.plugin.on import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg
from nonebot import get_driver
from nonebot.rule import Rule

current_dir = os.path.dirname(os.path.abspath(__file__))

config = get_driver().config
path = config.jmcomic_download_path  # 从环境变量读取


# path = r"D:\Project\SSbot\jmcomic_download"

def is_admin(bot: Bot, event: GroupMessageEvent) -> bool:
    return event.user_id in bot.config.superusers


async def async_download_album(id, option_path):
    opt = jmcomic.create_option_by_file(option_path)
    await asyncio.to_thread(jmcomic.download_album, id, opt)

jm = on_command("jm", aliases={"JM"}, rule=Rule(is_admin), priority=10, block=True)


# ————————代码文件逻辑说明——————————
# 命令文本格式：/jm {id}
# 运行逻辑：
# 接受并匹配指令
# 在QQ群内发送Downloading提示文本
# 提取id参数
# 启动JMCOIMC爬虫
# 文件下载完毕后上传至对应群里
# JMCOMIC爬虫：通过./option.yml文件设置 D:\Project\SSbot\jmcomic_download 为文件存储目录
# 下载文件后生成包含查询ID对应的{漫画名}.pdf和{id}.pdf文件
# 最终上传至QQ群的文件是{id}.pdf文件

@jm.handle()
async def my_jmcomic_plugin(bot: Bot, event: GroupMessageEvent, msg: Message = CommandArg()):
    nonebot.log.logger.info("_____________my_jmcomic_plugin_____________")

    id = msg.extract_plain_text().strip()
    if not id.isdigit():
        await jm.finish("ID 必须为数字", at_sender=True)

    nonebot.log.logger.info(f"开始下载漫画，ID: {id}, 群号: {event.group_id}")

    await jm.send("Downloading...", at_sender=True)

    option_path = os.path.join(current_dir, "option.yml")
    try:
        await async_download_album(id, option_path)
    except jmcomic.JmcomicException as e:
        await jm.finish(f"下载失败: {e}")
    except FileNotFoundError:
        await jm.finish("配置文件 option.yml 不存在")

    file = os.path.join(path, f"{id}.pdf")
    # "C:\\Users\\22321\\Desktop\\车卡\\未命名1.pdf"

    await bot.upload_group_file(
        group_id=event.group_id,
        file=file,
        namne=f"{id}.pdf"
    )




if __name__ == "__main__":
    # print(jmcomic.__file__)
    # JmOption.default().to_file('./option.yml')
    option = jmcomic.create_option_by_file('./option.yml')
    jmcomic.download_album(422866, option)
    # async_download_album(422866)
    pass
