# plugins/jm_downloader/config.py
from pathlib import Path
from pydantic import Field, BaseModel
from nonebot.plugin import get_plugin_config
from nonebot.log import logger

# 插件根目录：基于 __file__ 计算，与 CWD 无关
# 无论从哪个工作目录启动 bot，路径都能正确解析到插件自身的 data 目录
_PLUGIN_DIR = Path(__file__).parent


class PluginConfig(BaseModel):
    """Nonebot2 的 PluginConfig 基础类，用于从 Nonebot 环境加载配置"""
    class Config:
        extra = "ignore"


class JmDownloaderConfig(PluginConfig):
    """
    JM Downloader 插件的配置模型。
    所有路径默认值基于 __file__ 计算，确保跨环境可移植性。
    通过环境变量或 Nonebot 主配置可覆盖。
    """
    # 漫画下载和存储的基础路径
    # 默认: 插件目录/data/downloads
    jm_download_path: Path = Field(
        _PLUGIN_DIR / "data" / "downloads", env="JM_DOWNLOAD_PATH"
    )

    # jmcomic 库的选项文件路径
    # 默认: 插件目录/data/jmcomic_options.yml
    jmcomic_option_file: Path = Field(
        _PLUGIN_DIR / "data" / "jmcomic_options.yml", env="JMCOMIC_OPTION_FILE"
    )

    # 最大搜索结果数量
    max_search_results: int = Field(5, env="JM_MAX_SEARCH_RESULTS")

    # 文件上传后是否删除本地文件
    delete_after_upload: bool = Field(True, env="JM_DELETE_AFTER_UPLOAD")

    # 最大并发下载任务数
    max_concurrent_downloads: int = Field(3, env="JM_MAX_CONCURRENT_DOWNLOADS")

    def model_post_init(self, __context):
        """Pydantic v2 的 post-init 钩子，确保必要目录存在"""
        self.jm_download_path.mkdir(parents=True, exist_ok=True)
        if not self.jmcomic_option_file.exists():
            logger.warning(
                f"JMCOMIC option file not found at {self.jmcomic_option_file}. "
                "Using default option."
            )
