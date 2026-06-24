# plugins/jm_downloader/handlers/command_jm.py
from nonebot.plugin import on_command
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, PrivateMessageEvent, MessageEvent, Message
)
from nonebot.params import CommandArg
from nonebot.log import logger

from ..services.jm_downloader import JmDownloaderService, JmDownloaderServiceError
from ..builders.message_formatter import MessageFormatter

# 定义 Matcher 实例
# priority: 优先级，数字越小优先级越高
# block: True 表示此 Matcher 匹配后不再继续向下匹配其他 Matcher
jm_download_matcher = on_command("jm", aliases={"JM"}, priority=10, block=True)

# 注册依赖，这些实例将由 __init__.py 注入
_jm_downloader_service: JmDownloaderService = None
_message_formatter: MessageFormatter = None


def init_handler(jm_downloader_service: JmDownloaderService, message_formatter: MessageFormatter):
    """
    由插件 __init__.py 调用，注入服务实例。
    """
    global _jm_downloader_service, _message_formatter
    _jm_downloader_service = jm_downloader_service
    _message_formatter = message_formatter
    logger.info("command_jm 处理器服务注入完成。")


@jm_download_matcher.handle()
async def handle_jm_download(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """
    处理 /jm {id} 命令。
    私聊和群聊均可触发。
    """
    comic_id = args.extract_plain_text().strip()

    if not comic_id:
        await jm_download_matcher.send(
            _message_formatter.format_error_message("请提供漫画ID，例如：/jm 123456"),
            at_sender=True
        )
        return

    logger.info(f"接收到 /jm 命令，用户 {event.user_id} 请求下载漫画 ID: {comic_id}")

    await jm_download_matcher.send(
        _message_formatter.format_downloading_message(comic_id),
        at_sender=True
    )

    try:
        pdf_file_path = await _jm_downloader_service.download_and_convert_to_pdf(comic_id)

        await jm_download_matcher.send(_message_formatter.format_download_success_message(comic_id))

        # 按事件类型分支上传文件
        if isinstance(event, GroupMessageEvent):
            await bot.upload_group_file(
                group_id=event.group_id,
                file=str(pdf_file_path),
                name=pdf_file_path.name
            )
            logger.info(f"漫画 ID: {comic_id} 文件 {pdf_file_path.name} 已成功上传至群 {event.group_id}")
        elif isinstance(event, PrivateMessageEvent):
            await bot.upload_private_file(
                user_id=event.user_id,
                file=str(pdf_file_path),
                name=pdf_file_path.name
            )
            logger.info(f"漫画 ID: {comic_id} 文件 {pdf_file_path.name} 已成功上传至私聊用户 {event.user_id}")

    except JmDownloaderServiceError as e:
        await jm_download_matcher.send(
            _message_formatter.format_error_message(str(e)),
            at_sender=True
        )
        logger.error(f"下载漫画 {comic_id} 失败：{e}")
    except Exception as e:
        await jm_download_matcher.send(
            _message_formatter.format_error_message(f"下载和上传过程中发生未知错误: {e}"),
            at_sender=True
        )
        logger.exception(f"处理 /jm {comic_id} 命令时发生意外错误。")
    finally:
        if 'pdf_file_path' in locals():
            _jm_downloader_service.clean_up_download_files(pdf_file_path)
