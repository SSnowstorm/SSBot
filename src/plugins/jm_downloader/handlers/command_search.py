# plugins/jm_downloader/handlers/command_search.py
from nonebot.plugin import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message
from nonebot.params import CommandArg, EventPlainText
from nonebot.rule import to_me, Rule
from nonebot.log import logger
from nonebot.matcher import Matcher

from ..services.jm_downloader import JmDownloaderService, JmDownloaderServiceError
from ..services.state_manager import StateManager
from ..builders.message_formatter import MessageFormatter
from ..config import JmDownloaderConfig

# 定义 Matcher 实例
# 搜索命令
jm_search_matcher = on_command("jm_search", aliases={"jm search"}, priority=10, block=True)

# 搜索结果选择器 (监听数字输入)
# Rule.to_me() 表示需要 @机器人 或私聊
# StateManager 的作用就是在这里体现，用于维持用户的搜索状态
jm_select_matcher = on_message(
    Rule(),  # 默认匹配所有消息
    priority=11,  # 优先级略低于命令，高于一般消息
    block=False,  # 不阻塞，可能后面还有其他 on_message
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


@jm_search_matcher.handle()
async def handle_jm_search(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    """
    处理 `/jm search {keyword}` 命令。
    """
    keyword = args.extract_plain_text().strip()

    if not keyword:
        await jm_search_matcher.send(_message_formatter.format_error_message("请提供搜索关键词，例如：/jm search 异世界"),
                                     at_sender=True)
        return

    logger.info(f"接收到 /jm search 命令，用户 {event.user_id} 搜索关键词: {keyword}")

    await jm_search_matcher.send(_message_formatter.format_downloading_message(f"搜索 '{keyword}'", at_sender=True))

    try:
        # 调用业务逻辑服务进行搜索
        search_results = await _jm_downloader_service.search_comics(keyword)

        if not search_results:
            await jm_search_matcher.send(_message_formatter.format_search_results([]))
            return

        # 将搜索结果存储到 StateManager
        user_id_str = str(event.user_id)
        _state_manager.set_search_results(user_id_str, search_results)

        # 发送搜索结果给用户，并引导选择
        await jm_search_matcher.send(_message_formatter.format_search_results(
            search_results, _plugin_config.max_search_results
        ))

        # 将当前会话状态设置为等待用户选择
        jm_search_matcher.set_arg("user_id", Message(user_id_str))  # 将用户ID作为参数传递给下一个状态
        jm_search_matcher.set_arg("search_results", Message("sent"))  # 标记已发送搜索结果

        # 进入下一个状态，等待用户输入选择
        await jm_search_matcher.send("请回复序号选择您想要下载的漫画。", at_sender=True)
        await jm_search_matcher.pause()  # 暂停当前 matcher，等待用户的下一个输入


    except JmDownloaderServiceError as e:
        await jm_search_matcher.send(_message_formatter.format_error_message(str(e), at_sender=True))
        logger.error(f"搜索漫画 '{keyword}' 失败：{e}")
    except Exception as e:
        await jm_search_matcher.send(
            _message_formatter.format_error_message(f"搜索过程中发生未知错误: {e}", at_sender=True))
        logger.exception(f"处理 /jm search {keyword} 命令时发生意外错误。")


@jm_search_matcher.got("selection")  # 等待用户输入 'selection' 参数
async def handle_jm_selection(bot: Bot, event: GroupMessageEvent, selection: Message = EventPlainText()):
    """
    处理用户在搜索结果后的选择。
    """
    user_id_str = str(event.user_id)
    raw_selection = selection.strip()

    # 用户选择取消
    if raw_selection.lower() == "取消":
        _state_manager.clear_search_results(user_id_str)
        await jm_search_matcher.finish(_message_formatter.format_cancel_message())
        return

    # 尝试将输入转换为数字
    try:
        index = int(raw_selection) - 1  # 用户输入是1开始的序号
        if index < 0:
            raise ValueError
    except ValueError:
        await jm_search_matcher.reject(_message_formatter.format_invalid_selection_message())
        return

    # 从 StateManager 获取之前的搜索结果
    search_results = _state_manager.get_search_results(user_id_str)

    if not search_results or not (0 <= index < len(search_results)):
        await jm_search_matcher.reject(_message_formatter.format_invalid_selection_message())
        return

    selected_comic = search_results[index]
    comic_id = selected_comic.id

    logger.info(f"用户 {event.user_id} 选择了漫画 ID: {comic_id} ('{selected_comic.title}') 进行下载。")

    # 提示用户已选择并即将下载
    await jm_search_matcher.send(_message_formatter.format_selected_comic_info(selected_comic))
    await jm_search_matcher.send(_message_formatter.format_downloading_message(comic_id, at_sender=True))

    try:
        # 调用业务逻辑服务进行下载
        pdf_file_path = await _jm_downloader_service.download_and_convert_to_pdf(comic_id)

        # 提示用户文件已准备好并开始上传
        await jm_search_matcher.send(_message_formatter.format_download_success_message(comic_id))

        # 上传文件到群组
        await bot.upload_group_file(
            group_id=event.group_id,
            file=str(pdf_file_path),
            name=pdf_file_path.name
        )
        logger.info(f"漫画 ID: {comic_id} 文件 {pdf_file_path.name} 已成功上传至群 {event.group_id}")

    except JmDownloaderServiceError as e:
        await jm_search_matcher.send(_message_formatter.format_error_message(str(e), at_sender=True))
        logger.error(f"下载漫画 {comic_id} 失败：{e}")
    except Exception as e:
        await jm_search_matcher.send(
            _message_formatter.format_error_message(f"下载和上传过程中发生未知错误: {e}", at_sender=True))
        logger.exception(f"处理漫画 {comic_id} 选择下载时发生意外错误。")
    finally:
        # 清理用户的搜索状态
        _state_manager.clear_search_results(user_id_str)
        # 无论成功失败，都尝试清理文件（如果配置允许）
        if 'pdf_file_path' in locals():
            _jm_downloader_service.clean_up_download_files(pdf_file_path)
