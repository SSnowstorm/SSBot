# plugins/jm_downloader/services/jm_downloader.py
import asyncio
from pathlib import Path
from typing import List, Optional

from nonebot.log import logger

from ..config import JmDownloaderConfig
from ..models.comic_data import ComicInfo
from .jm_api import JmApi, JmApiError, JmComicNotFoundError


class JmDownloaderServiceError(Exception):
    """JM Downloader 服务的自定义异常基类"""
    pass


class JmDownloaderService:
    """
    JM 下载服务的核心业务逻辑层。
    负责编排 JmApi 的调用，处理下载文件路径，以及清理逻辑。
    """

    def __init__(self, config: JmDownloaderConfig, jm_api: JmApi):
        self.config = config
        self.jm_api = jm_api
        # 使用 asyncio.Semaphore 限制并发下载数量
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_downloads)
        logger.info(f"JM Downloader 服务初始化完成，最大并发下载: {self.config.max_concurrent_downloads}")

    async def download_and_convert_to_pdf(self, comic_id: str) -> Path:
        """
        下载指定ID的漫画并确保生成PDF文件。
        这是整个下载流程的核心业务方法。
        """
        async with self._semaphore:  # 使用信号量控制并发
            logger.info(f"开始处理下载请求，漫画ID: {comic_id}")
            try:
                # 调用 JmApi 下载原始漫画文件
                pdf_file_path = await self.jm_api.download_raw_comic(comic_id)

                # 确保文件存在，jm_api已经做了检查，这里再次确认
                if not pdf_file_path.is_file():
                    raise JmDownloaderServiceError(
                        f"漫画 {comic_id} 下载完成，但未能找到生成的PDF文件: {pdf_file_path}"
                    )

                logger.info(f"漫画 {comic_id} 的PDF文件已就绪: {pdf_file_path}")
                return pdf_file_path
            except JmComicNotFoundError as e:
                logger.warning(f"用户请求下载的漫画 {comic_id} 未找到。")
                raise JmDownloaderServiceError(f"未找到漫画 {comic_id}，请检查ID是否正确。") from e
            except JmApiError as e:
                logger.error(f"下载漫画 {comic_id} 时发生API错误: {e}")
                raise JmDownloaderServiceError(f"下载失败: {e}") from e
            except Exception as e:
                logger.exception(f"下载漫画 {comic_id} 时发生未知错误。")
                raise JmDownloaderServiceError(f"未知错误导致下载失败: {e}") from e

    async def search_comics(self, keyword: str) -> List[ComicInfo]:
        """
        根据关键词搜索漫画，并返回结构化的 ComicInfo 列表。
        """
        logger.info(f"服务层接收搜索请求，关键词: {keyword}")
        try:
            # 调用 JmApi 进行搜索，获取原始字典列表
            raw_results = await self.jm_api.search_comics(keyword)

            # 将原始字典列表转换为 ComicInfo 模型列表
            comic_infos: List[ComicInfo] = []
            for item in raw_results:
                try:
                    comic_infos.append(ComicInfo(**item))
                except Exception as e:
                    logger.warning(f"转换搜索结果到 ComicInfo 模型失败: {item}. 错误: {e}")

            logger.info(f"搜索关键词 '{keyword}' 成功，找到 {len(comic_infos)} 个符合条件的漫画。")
            return comic_infos
        except JmApiError as e:
            logger.error(f"搜索漫画关键词 '{keyword}' 时发生API错误: {e}")
            raise JmDownloaderServiceError(f"搜索失败: {e}") from e
        except Exception as e:
            logger.exception(f"搜索漫画关键词 '{keyword}' 时发生未知错误。")
            raise JmDownloaderServiceError(f"未知错误导致搜索失败: {e}") from e

    def clean_up_download_files(self, file_path: Path):
        """
        根据配置决定是否删除下载的PDF文件。
        """
        if self.config.delete_after_upload:
            try:
                if file_path.is_file():
                    file_path.unlink()  # 删除文件
                    logger.info(f"已删除下载的PDF文件: {file_path}")
                else:
                    logger.warning(f"尝试删除文件失败，文件不存在: {file_path}")
            except Exception as e:
                logger.error(f"删除文件 {file_path} 时发生错误: {e}")
