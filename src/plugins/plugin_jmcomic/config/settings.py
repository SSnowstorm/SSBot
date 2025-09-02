from pathlib import Path
from nonebot import get_driver


class Config:
    def __init__(self):
        self.jmcomic_download_path = Path("D:/Project/SSbot/jmcomic_download")
        self.max_concurrent_downloads = 3  # 最大并发下载数


config = get_driver().config
plugin_config = Config()
