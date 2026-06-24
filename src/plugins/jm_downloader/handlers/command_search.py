# plugins/jm_downloader/handlers/command_search.py
from nonebot.plugin import on_command, on_message
from nonebot.adapters.onebot.v11 import (
    Bot, GroupMessageEvent, PrivateMessageEvent, MessageEvent, Message
)
from nonebot.params import CommandArg
from nonebot.rule import Rule
from nonebot.log import logger

from ..services.jm_downloader import JmDownloaderService, JmDownloaderServiceError
from ..services.state_manager import StateManager
from ..builders.message_formatter import MessageFormatter
from ..config import JmDownloaderConfig

# 搜索命令（私聊和群聊均可触发）
jm_search_matcher = on_command("jm_search", aliases={"jm search"}, priority=10, block=True)

# 搜索结果选择监听器
# 通过 rule 过滤，只处理有活跃搜索会话的用户消息
# block=False：非数字/取消的消息放行，不干扰用户正常聊天
jm_select_matcher = on_message(
    priority=11,
    block=False,
)

# 注册依赖，这些实例将由 __init__.py 注入
_jm_downloader_service: JmDownloaderService = None
_state_manager: StateManager = None
_message_formatter: MessageFormatter = None
_plugin_config: JmDownloaderConfig = None


def init_handler(
    jm_downloader_service: JmDownloaderService,
    state_manager: StateManager,
    message_formatter: MessageFormatter,
    plugin_config: JmDownloaderConfig
):
    """
    由插件 __init__.py 调用，注入服务实例。
    """
    global _jm_downloader_service, _state_manager, _message_formatter, _plugin_config
    _jm_downloader_service = jm_downloader_service
    _state_manager = state_manager
    _message_formatter = message_formatter
    _plugin_config = plugin_config
    logger.info("command_search 处理器服务注入完成。")


def _get_group_id(event: MessageEvent):
    """从事件中提取 group_id，私聊时返回 None。"""
    return getattr(event, 'group_id', None)


# ========== 搜索命令 handler ==========

@jm_search_matcher.handle()
async def handle_jm_search(event: MessageEvent, args: Message = CommandArg()):
    """
    处理 /jm_search {keyword} 命令。
    私聊和群聊均可触发。
    """
    keyword = args.extract_plain_text().strip()

    if not keyword:
        await jm_search_matcher.send(
            _message_formatter.format_error_message("请提供搜索关键词，例如：/jm_search 异世界"),
            at_sender=True
        )
        return

    group_id = _get_group_id(event)
    logger.info(f"接收到 /jm_search 命令，用户 {event.user_id} (群 {group_id}) 搜索关键词: {keyword}")

    await jm_search_matcher.send(
        _message_formatter.format_searching_message(keyword),
        at_sender=True
    )

    try:
        search_results = await _jm_downloader_service.search_comics(keyword)

        if not search_results:
            await jm_search_matcher.send("抱歉，未能找到符合条件的漫画。")
            return

        # 存储搜索结果到 StateManager，key 为 (group_id, user_id)
        _state_manager.set_search_results(group_id, event.user_id, search_results)

        # 发送搜索结果列表
        await jm_search_matcher.send(
            _message_formatter.format_search_results(
                search_results, _plugin_config.max_search_results
            )
        )

    except JmDownloaderServiceError as e:
        await jm_search_matcher.send(
            _message_formatter.format_error_message(str(e)),
            at_sender=True
        )
        logger.error(f"搜索漫画 '{keyword}' 失败：{e}")
    except Exception as e:
        await jm_search_matcher.send(
            _message_formatter.format_error_message(f"搜索过程中发生未知错误: {e}"),
            at_sender=True
        )
        logger.exception(f"处理 /jm_search {keyword} 命令时发生意外错误。")


# ========== 选择监听 handler ==========

async def _has_active_session(event: MessageEvent) -> bool:
    """
    Rule 函数：检查发送者是否有活跃的搜索会话。
    只在有活跃会话时才进入 handler，避免对普通消息产生干扰。
    """
    if _state_manager is None:
        return False
    group_id = _get_group_id(event)
    return _state_manager.is_active(group_id, event.user_id)


# 动态设置 rule（需要 _state_manager 已注入后才能生效，但 rule 在运行时求值）
jm_select_matcher.rule = Rule(_has_active_session)


@jm_select_matcher.handle()
async def handle_jm_selection(bot: Bot, event: MessageEvent):
    """
    处理用户在搜索结果后的选择。
    仅当用户有活跃搜索会话时触发（由 _has_active_session rule 保证）。
    支持私聊和群聊。
    """
    group_id = _get_group_id(event)
    raw_input = event.get_plaintext().strip()

    # 用户取消
    if raw_input.lower() in ("取消", "cancel", "c"):
        _state_manager.clear_search_results(group_id, event.user_id)
        await jm_select_matcher.send(_message_formatter.format_cancel_message())
        return

    # 尝试解析数字序号
    try:
        index = int(raw_input) - 1
        if index < 0:
            return  # 负数或0，不是有效选择，放行
    except ValueError:
        return  # 非数字，不是选择指令，放行（让用户正常聊天）

    # 获取搜索结果
    search_results = _state_manager.get_search_results(group_id, event.user_id)

    if not search_results or not (0 <= index < len(search_results)):
        await jm_select_matcher.send(_message_formatter.format_invalid_selection_message())
        return

    selected_comic = search_results[index]
    comic_id = selected_comic.id

    logger.info(f"用户 {event.user_id} 选择了漫画 ID: {comic_id} ('{selected_comic.title}') 进行下载。")

    await jm_select_matcher.send(_message_formatter.format_selected_comic_info(selected_comic))
    await jm_select_matcher.send(_message_formatter.format_downloading_message(comic_id))

    try:
        pdf_file_path = await _jm_downloader_service.download_and_convert_to_pdf(comic_id)

        await jm_select_matcher.send(_message_formatter.format_download_success_message(comic_id))

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
        await jm_select_matcher.send(
            _message_formatter.format_error_message(str(e)),
            at_sender=True
        )
        logger.error(f"下载漫画 {comic_id} 失败：{e}")
    except Exception as e:
        await jm_select_matcher.send(
            _message_formatter.format_error_message(f"下载和上传过程中发生未知错误: {e}"),
            at_sender=True
        )
        logger.exception(f"处理漫画 {comic_id} 选择下载时发生意外错误。")
    finally:
        # 无论成功失败，清理搜索会话状态
        _state_manager.clear_search_results(group_id, event.user_id)
        # 清理临时文件
        if 'pdf_file_path' in locals():
            _jm_downloader_service.clean_up_download_files(pdf_file_path)
