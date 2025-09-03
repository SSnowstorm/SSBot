# plugins/jm_downloader/services/state_manager.py
from typing import Dict, List, Optional
from ..models.comic_data import ComicInfo


class StateManager:
    """
    管理用户会话状态的服务，主要用于存储搜索结果，以便用户后续进行选择。
    目前使用内存字典存储，考虑持久化可以替换为Redis等。
    """

    def __init__(self):
        # 存储用户ID到其最近搜索结果列表的映射
        # Key: str (用户ID), Value: List[ComicInfo] (搜索结果)
        self._user_search_results: Dict[str, List[ComicInfo]] = {}

    def set_search_results(self, user_id: str, results: List[ComicInfo]):
        """
        为指定用户存储搜索结果。
        """
        self._user_search_results[user_id] = results

    def get_search_results(self, user_id: str) -> Optional[List[ComicInfo]]:
        """
        获取指定用户的最近搜索结果。
        """
        return self._user_search_results.get(user_id)

    def clear_search_results(self, user_id: str):
        """
        清除指定用户的搜索结果。
        """
        if user_id in self._user_search_results:
            del self._user_search_results[user_id]
