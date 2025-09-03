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
        logger.info(f"JMCOMIC API 服务初始化完成，选项文件: {self.config.jmcomic_option_file}")

    def _load_jmcomic_option(self) -> jmcomic.JmOption:
        """
        加载 jmcomic 库的配置文件。
        """
        option_file = self.config.jmcomic_option_file
        if not option_file.exists():
            # 如果文件不存在，尝试创建一个默认的并提示用户
            # 在实际生产环境中，可能需要更完善的默认文件创建逻辑
            logger.warning(
                f"JMCOMIC option file not found at {option_file}. "
                "Attempting to create a default one. Please review and customize."
            )
            # JmOption.default().to_file(option_file) # jmcomic 库的默认创建方法
            # 简化处理，直接返回默认选项
            return jmcomic.JmOption.default()

        return jmcomic.create_option_by_file(str(option_file))

    async def download_raw_comic(self, comic_id: str) -> Path:
        """
        异步下载指定ID的漫画。
        注意：jmcomic.download_album 是同步阻塞操作，这里通过 asyncio.to_thread 转换为异步。
        它会返回下载后的文件路径。这里假设 jmcomic 库直接生成了 PDF 文件。
        """
        logger.info(f"开始下载漫画 ID: {comic_id}")
        download_dir = self.config.jm_download_path

        # JMCOMIC 库的 Option 对象需要设置下载目录
        # 这里需要创建一个新的 option 实例或修改已有的，确保下载到指定目录
        # 假设 jmcomic.create_option_by_file 内部也允许指定下载目录
        # 或者在 _jm_option 中动态修改，这取决于 jmcomic 库的具体 API
        # 为了演示，我们假设 jmcomic.download_album 会使用 _jm_option 里的路径，
        # 且 _jm_option 可以在外部设置下载路径

        # 实际操作中，jmcomic库的download_album方法可能需要修改option对象的download_dir属性
        # 这里为了简化，假设_jm_option已经正确配置了下载路径
        # 如果 jmcomic.JmOption 不支持运行时修改下载路径，可能需要每次都创建

        # 为了演示，确保下载路径在option中被正确设置 (如果jmcomic支持)
        self._jm_option.download_dir = str(download_dir)

        try:
            # jmcomic.download_album 可能会返回下载的路径或一个状态
            # 这里假设它返回的是一个包含 PDF 文件的目录路径或直接的 PDF 文件路径
            # 原始代码是拼接 {id}.pdf，所以我们也返回期望的 PDF 路径

            # 由于 jmcomic 库的 download_album 是同步阻塞的，所以需要将其放入线程池
            # jmcomic.download_album(comic_id, self._jm_option)
            # 原始代码中生成了 {id}.pdf 和 {漫画名}.pdf，我们以 {id}.pdf 为目标
            await asyncio.to_thread(jmcomic.download_album, comic_id, self._jm_option)

            # 假设下载完成后，会在 download_dir 中生成名为 "{id}.pdf" 的文件
            pdf_path = download_dir / f"{comic_id}.pdf"
            if not pdf_path.exists():
                logger.error(f"漫画 {comic_id} 下载完成，但未找到预期的 PDF 文件：{pdf_path}")
                raise JmApiError(f"漫画 {comic_id} 下载失败或未生成 PDF 文件。")

            logger.info(f"漫画 ID: {comic_id} 下载成功，文件路径: {pdf_path}")
            return pdf_path
        except jmcomic.JmcomicException as e:
            # 捕获 jmcomic 库可能抛出的特定异常
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
        注意：jmcomic 库的原始示例中没有直接的搜索API。
        这里假设 jmcomic 提供了 `jmcomic.search_comic(keyword, option)` 类似的API。
        如果实际没有，你需要根据 jmcomic 的文档进行调整，或者自行实现爬取搜索页面的逻辑。
        """
        logger.info(f"开始搜索漫画，关键词: {keyword}")
        try:
            # 假设 jmcomic.search_comic 是一个同步阻塞函数
            # 它返回一个字典列表，每个字典包含漫画的原始数据
            # 例如: [{"id": "123", "title": "xxx", ...}]

            # --- START MOCK JMCOMIC SEARCH API ---
            # 这是对 jmcomic.search_comic 的一个模拟，如果库本身没有此API，你需要自行实现
            # 或者通过 JMCOMIC 的某种高级选项来触发搜索
            await asyncio.sleep(1)  # 模拟网络请求延迟
            mock_results = []
            if "示例" in keyword:
                mock_results = [
                    {"id": "100001", "title": "示例漫画一", "author": "作者A", "tags": ["奇幻", "冒险"],
                     "cover_url": "http://example.com/cover1.jpg"},
                    {"id": "100002", "title": "示例漫画二", "author": "作者B", "tags": ["科幻", "日常"],
                     "cover_url": "http://example.com/cover2.jpg"},
                    {"id": "100003", "title": "示例漫画三", "author": "作者A", "tags": ["奇幻", "爱情"],
                     "cover_url": "http://example.com/cover3.jpg"},
                ]
            elif "测试" in keyword:
                mock_results = [
                    {"id": "200001", "title": "测试作品", "author": "测试者", "tags": ["测试"],
                     "cover_url": "http://example.com/cover_test.jpg"},
                ]
            else:
                return []

            # 根据配置限制返回结果数量
            results = mock_results[:self.config.max_search_results]
            # --- END MOCK JMCOMIC SEARCH API ---

            # 真实情况下，这里应该是：
            # raw_results = await asyncio.to_thread(jmcomic.search_comic, keyword, self._jm_option)
            # results = raw_results[:self.config.max_search_results]

            logger.info(f"搜索关键词 '{keyword}' 找到 {len(results)} 个结果。")
            return results
        except Exception as e:
            logger.exception(f"搜索漫画关键词 '{keyword}' 时发生错误。")
            raise JmApiError(f"搜索失败: {e}") from e

    async def get_comic_details(self, comic_id: str) -> Optional[Dict[str, Any]]:
        """
        异步获取指定ID漫画的详细信息。
        同样，假设 jmcomic 提供了 `jmcomic.get_comic_info(id, option)` 类似的API。
        """
        logger.info(f"开始获取漫画 ID: {comic_id} 的详情。")
        try:
            # 假设 jmcomic.get_comic_info 是一个同步阻塞函数
            # 它返回一个字典，包含漫画的详细数据

            # --- START MOCK JMCOMIC GET DETAILS API ---
            await asyncio.sleep(0.5)  # 模拟网络请求延迟
            if comic_id == "100001":
                details = {"id": "100001", "title": "示例漫画一", "author": "作者A",
                           "tags": ["奇幻", "冒险"], "cover_url": "http://example.com/cover1.jpg",
                           "description": "这是一部关于奇幻世界冒险的漫画。", "pages": 50}
            elif comic_id == "422866":  # 对应原始代码中的测试ID
                details = {"id": "422866", "title": "测试漫画 (原代码ID)", "author": "测试作者",
                           "tags": ["测试", "PDF"], "cover_url": "http://example.com/cover_test.jpg",
                           "description": "这是用于测试的漫画，可以下载成PDF。", "pages": 20}
            else:
                details = None
            # --- END MOCK JMCOMIC GET DETAILS API ---

            # 真实情况下，这里应该是：
            # details = await asyncio.to_thread(jmcomic.get_comic_info, comic_id, self._jm_option)

            if details:
                logger.info(f"成功获取漫画 ID: {comic_id} 的详情。")
            else:
                logger.warning(f"未找到漫画 ID: {comic_id} 的详情。")
            return details
        except Exception as e:
            logger.exception(f"获取漫画 {comic_id} 详情时发生错误。")
            raise JmApiError(f"获取详情失败: {e}") from e