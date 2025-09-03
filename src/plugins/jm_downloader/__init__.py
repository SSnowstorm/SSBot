# plugins/jm_downloader/__init__.py
from nonebot import require, get_plugin_config
from nonebot.plugin import Plugin
from nonebot.log import logger

# 导入所有需要注册的 Matcher (它们会自动被 Nonebot2 发现)
from .handlers import command_jm, command_search

# 导入配置模型和所有服务、构建器
from .config import JmDownloaderConfig
from .services.jm_api import JmApi
from .services.jm_downloader import JmDownloaderService
from .services.state_manager import StateManager
from .builders.message_formatter import MessageFormatter

# 初始化插件
plugin = Plugin(name="JM Downloader Plugin")


@plugin.on_load
async def plugin_on_load():
    """
    插件加载时执行的初始化逻辑。
    负责实例化配置、服务和构建器，并将它们注入到处理器中。
    """
    logger.info("开始加载 JM Downloader 插件...")

    # 1. 加载插件配置
    plugin_config = get_plugin_config(JmDownloaderConfig)
    logger.info(f"插件配置加载完成: {plugin_config.dict()}")

    # 2. 实例化核心服务和消息构建器
    jm_api_service = JmApi(plugin_config)
    jm_downloader_service = JmDownloaderService(plugin_config, jm_api_service)
    state_manager = StateManager()
    message_formatter = MessageFormatter()

    # 3. 将服务实例注入到各个 Handler 中
    # 这是实现依赖注入的一种简单方式，避免了外部库的引入
    command_jm.init_handler(jm_downloader_service, message_formatter)
    command_search.init_handler(jm_downloader_service, state_manager, message_formatter, plugin_config)

    logger.info("JM Downloader 插件加载完毕，所有服务已注入。")
