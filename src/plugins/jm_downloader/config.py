# plugins/jm_downloader/config.py
from pathlib import Path
from pydantic import Field, BaseModel
from nonebot import get_plugin_config
from nonebot.log import logger


# Nonebot2 的 PluginConfig 基础类，用于从 Nonebot 环境加载配置
class PluginConfig(BaseModel):
    class Config:
        extra = "ignore"  # 忽略 Nonebot 配置文件中多余的字段


class JmDownloaderConfig(PluginConfig):
    """
    JM Downloader 插件的配置模型。
    通过 Nonebot2 的配置系统加载，支持从环境变量或 Nonebot 主配置中读取。
    """
    # 漫画下载和存储的基础路径，默认为插件data目录下的downloads子目录
    # 可通过环境变量 JM_DOWNLOAD_PATH 覆盖
    jm_download_path: Path = Field(
        Path("data/jm_downloader/downloads"), env="JM_DOWNLOAD_PATH"
    )

    # jmcomic 库的选项文件路径，默认为插件data目录下的jmcomic_options.yml
    # 可通过环境变量 JMCOMIC_OPTION_FILE 覆盖
    jmcomic_option_file: Path = Field(
        Path("data/jm_downloader/jmcomic_options.yml"), env="JMCOMIC_OPTION_FILE"
    )

    # 最大搜索结果数量，用于限制返回给用户的搜索结果列表长度
    # 可通过环境变量 JM_MAX_SEARCH_RESULTS 覆盖
    max_search_results: int = Field(5, env="JM_MAX_SEARCH_RESULTS")

    # 文件上传后是否删除本地文件
    # 可通过环境变量 JM_DELETE_AFTER_UPLOAD 覆盖
    delete_after_upload: bool = Field(True, env="JM_DELETE_AFTER_UPLOAD")

    # 最大并发下载任务数，防止过多的下载任务导致资源耗尽或被 JMCOMIC 封禁
    # 可通过环境变量 JM_MAX_CONCURRENT_DOWNLOADS 覆盖
    max_concurrent_downloads: int = Field(3, env="JM_MAX_CONCURRENT_DOWNLOADS")

    def __post_init__(self):
        """
        配置加载后的初始化，确保必要的目录存在。
        """
        # 确保下载路径存在
        self.jm_download_path.mkdir(parents=True, exist_ok=True)
        # 如果 jmcomic option 文件不存在，可以尝试创建一个默认的
        if not self.jmcomic_option_file.exists():
            logger.warning(
                f"JMCOMIC option file not found at {self.jmcomic_option_file}. "
                "Please create it or configure the correct path."
            )

# 通过 Nonebot2 的 get_plugin_config 方法获取配置实例
# 这样可以在插件的任何地方导入并使用这个唯一的配置实例
# config = get_plugin_config(JmDownloaderConfig)
