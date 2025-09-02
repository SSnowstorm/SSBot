from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.params import CommandArg
from pathlib import Path
from ..core.downloader import JmcomicDownloader
from ..core.uploader import QQUploader
from ..models.task import DownloadTask
from ..utils.logger import logger
from ..config import plugin_config

jm = on_command("jm", aliases=["JM"], priority=10, block=True)


@jm.handle()
async def handle_jm_command(
        bot: Bot,
        event: GroupMessageEvent,
        msg: str = CommandArg()
):
    task = DownloadTask(
        album_id=msg.extract_plain_text().strip(),
        requester_id=event.user_id,
        group_id=event.group_id
    )

    if not task.validate():
        await jm.finish("无效的漫画ID，请输入6位数字")

    await jm.send("开始下载，请稍候...")

    try:
        # 初始化服务
        downloader = JmcomicDownloader(
            Path(__file__).parent.parent / "config" / "jmcomic_config.yml"
        )
        uploader = QQUploader()

        # 执行下载
        pdf_path = await downloader.download_album(task)

        # 执行上传
        if pdf_path and await uploader.upload_pdf(bot, task.group_id, pdf_path):
            await jm.finish(f"上传成功: {pdf_path.name}")
        else:
            await jm.finish("文件处理失败")

    except Exception as e:
        logger.exception("处理流程异常")
        await jm.finish(f"操作失败: {str(e)}")