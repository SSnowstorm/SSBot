# plugins/jm_downloader/__init__.py
from nonebot import get_plugin_config
from nonebot.log import logger

# 导入所有需要注册的 Matcher (它们会自动被 Nonebot2 发现)
from .handlers import command_jm, command_search

# 导入配置模型和所有服务、构建器
from .config import JmDownloaderConfig
from .services.jm_api import JmApi
from .services.jm_downloader import JmDownloaderService
from .services.state_manager import StateManager
from .builders.message_formatter import MessageFormatter

logger.info("开始加载 JM Downloader 插件...")

# 模块级初始化：NoneBot2 在 nonebot.init() 之后才加载插件，此时配置已可用。
# 直接在 import 时完成服务实例化和注入，无需额外的生命周期注册。

# 1. 加载插件配置
plugin_config = get_plugin_config(JmDownloaderConfig)

# 确保下载目录存在（config.py 的 __post_init__ 在 Pydantic 中不会被调用，这里手动确保）
plugin_config.jm_download_path.mkdir(parents=True, exist_ok=True)

# 2. 实例化核心服务和消息构建器
jm_api_service = JmApi(plugin_config)
jm_downloader_service = JmDownloaderService(plugin_config, jm_api_service)
state_manager = StateManager()
message_formatter = MessageFormatter()

# 3. 将服务实例注入到各个 Handler 中
command_jm.init_handler(jm_downloader_service, message_formatter)
command_search.init_handler(jm_downloader_service, state_manager, message_formatter, plugin_config)

logger.info("JM Downloader 插件加载完毕，所有服务已注入。")
