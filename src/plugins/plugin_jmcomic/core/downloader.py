import asyncio
import jmcomic
from pathlib import Path
from typing import Optional

from ..config.settings import plugin_config
from ..utils.logger import logger
from ..models.task import DownloadTask


class JmcomicDownloader:
    def __init__(self, config_path: Path):
        self.option = jmcomic.create_option_by_file(config_path)

    async def download_album(self, task: DownloadTask) -> Optional[Path]:
        """通过 jmcomic 下载漫画，返回生成的PDF路径"""
        try:
            logger.info(f"开始下载任务: {task.album_id}")

            # 调用下载（不传递output_path，依赖option.yml的dir_rule配置）
            await asyncio.to_thread(
                jmcomic.download_album,
                task.album_id,
                self.option
            )

            # 返回下载的文件（通过album_id模糊匹配）
            return self._find_downloaded_file(task.album_id)

        except Exception as e:
            logger.error(f"下载失败: {e}")
            raise

    def _find_downloaded_file(self, album_id: str) -> Optional[Path]:
        """根据album_id在下载目录中查找最新生成的PDF"""
        pdf_files = list(plugin_config.jmcomic_download_path.glob(f"*{album_id}*.pdf"))
        return pdf_files[0] if pdf_files else None
