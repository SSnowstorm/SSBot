# plugins/jm_downloader/services/jm_api.py
import asyncio
import jmcomic
from pathlib import Path
from typing import Dict, List, Any, Optional

from nonebot.log import logger

from ..config import JmDownloaderConfig
from ..models.comic_data import ComicInfo


class JmApiError(Exception):
    """JMCOMIC API 相关的自定义异常基类"""
    pass


class JmComicNotFoundError(JmApiError):
    """当指定的漫画ID不存在时抛出"""

    def __init__(self, comic_id: str):
        super().__init__(f"漫画ID {comic_id} 未找到或不存在。")
        self.comic_id = comic_id


class JmApiRateLimitError(JmApiError):
    """当JMCOMIC API 触发限流时抛出"""

    def __init__(self, message: str = "JMCOMIC API 请求过于频繁，请稍后再试。"):
        super().__init__(message)


class JmApi:
    """
    封装 JMCOMIC 库的底层 API 调用。
    负责与 jmcomic 库的直接交互，管理其配置，并提供异步接口。
    """

    def __init__(self, config: JmDownloaderConfig):
        self.config = config
        self._jm_option = self._load_jmcomic_option()
        self._client = self._jm_option.new_jm_client()
        logger.info(f"JMCOMIC API 服务初始化完成，选项文件: {self.config.jmcomic_option_file}")

    def _load_jmcomic_option(self) -> jmcomic.JmOption:
        """
        加载 jmcomic 库的配置文件。
        """
        option_file = self.config.jmcomic_option_file
        if not option_file.exists():
            logger.warning(
                f"JMCOMIC option file not found at {option_file}. "
                "Using default option. Please review and customize."
            )
            return jmcomic.JmOption.default()

        return jmcomic.create_option_by_file(str(option_file))

    async def download_raw_comic(self, comic_id: str) -> Path:
        """
        异步下载指定ID的漫画。
        jmcomic.download_album 是同步阻塞操作，通过 asyncio.to_thread 转换为异步。
        """
        logger.info(f"开始下载漫画 ID: {comic_id}")
        download_dir = self.config.jm_download_path

        self._jm_option.download_dir = str(download_dir)

        try:
            await asyncio.to_thread(jmcomic.download_album, comic_id, self._jm_option)

            pdf_path = download_dir / f"{comic_id}.pdf"
            if not pdf_path.exists():
                logger.error(f"漫画 {comic_id} 下载完成，但未找到预期的 PDF 文件：{pdf_path}")
                raise JmApiError(f"漫画 {comic_id} 下载失败或未生成 PDF 文件。")

            logger.info(f"漫画 ID: {comic_id} 下载成功，文件路径: {pdf_path}")
            return pdf_path
        except jmcomic.JmcomicException as e:
            if "not found" in str(e).lower() or "不存在" in str(e):
                raise JmComicNotFoundError(comic_id) from e
            elif "too many requests" in str(e).lower() or "频率过高" in str(e):
                raise JmApiRateLimitError() from e
            logger.exception(f"下载漫画 {comic_id} 时发生 JMCOMIC 库错误。")
            raise JmApiError(f"JMCOMIC 库错误: {e}") from e
        except Exception as e:
            logger.exception(f"下载漫画 {comic_id} 时发生未知错误。")
            raise JmApiError(f"未知错误: {e}") from e

    async def search_comics(self, keyword: str) -> List[Dict[str, Any]]:
        """
        异步搜索漫画。
        使用 jmcomic 库的 client.search_site() 接口。
        返回原始字典列表，每个字典包含 id, title, tags 等字段。
        """
        logger.info(f"开始搜索漫画，关键词: {keyword}")
        try:
            def _sync_search():
                page = self._client.search_site(search_query=keyword, page=1)
                results = []
                for aid, title, tags in page.iter_id_title_tag():
                    results.append({
                        "id": str(aid),
                        "title": title,
                        "tags": list(tags) if tags else [],
                        "author": None,
                        "cover_url": None,
                    })
                return results[:self.config.max_search_results]

            results = await asyncio.to_thread(_sync_search)
            logger.info(f"搜索关键词 '{keyword}' 找到 {len(results)} 个结果。")
            return results
        except Exception as e:
            logger.exception(f"搜索漫画关键词 '{keyword}' 时发生错误。")
            raise JmApiError(f"搜索失败: {e}") from e

    async def get_comic_details(self, comic_id: str) -> Optional[Dict[str, Any]]:
        """
        异步获取指定ID漫画的详细信息。
        使用 jmcomic 库的 client.get_album_detail() 接口。
        """
        logger.info(f"开始获取漫画 ID: {comic_id} 的详情。")
        try:
            def _sync_get_details():
                album = self._client.get_album_detail(comic_id)

                author = getattr(album, 'author', None)
                if isinstance(author, (list, tuple)):
                    author = ", ".join(str(a) for a in author)
                elif author is not None:
                    author = str(author)

                return {
                    "id": str(getattr(album, 'album_id', comic_id)),
                    "title": getattr(album, 'title', '未知标题'),
                    "author": author,
                    "tags": list(getattr(album, 'tags', []) or []),
                    "cover_url": None,
                    "description": getattr(album, 'description', None) or getattr(album, 'intro', None),
                    "pages": getattr(album, 'page_count', None),
                }

            details = await asyncio.to_thread(_sync_get_details)
            if details:
                logger.info(f"成功获取漫画 ID: {comic_id} 的详情。")
            else:
                logger.warning(f"未找到漫画 ID: {comic_id} 的详情。")
            return details
        except Exception as e:
            logger.exception(f"获取漫画 {comic_id} 详情时发生错误。")
            raise JmApiError(f"获取详情失败: {e}") from e
