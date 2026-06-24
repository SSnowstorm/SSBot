# plugins/jm_downloader/services/state_manager.py
import time
from typing import Dict, List, Optional, Tuple

from ..models.comic_data import ComicInfo


class SearchSession:
    """
    单次搜索会话的数据容器。
    """

    def __init__(self, results: List[ComicInfo], group_id: Optional[int], user_id: int):
        self.results = results
        self.group_id = group_id
        self.user_id = user_id
        self.created_at = time.time()


class StateManager:
    """
    管理用户搜索会话状态的服务。
    使用 (group_id, user_id) 元组作为 key 实现群隔离 + 私聊支持。
    内存存储，带超时自动过期机制。
    """

    # 会话超时时间（秒），默认 5 分钟
    SESSION_TIMEOUT = 300

    def __init__(self):
        # Key: (group_id_or_None, user_id), Value: SearchSession
        self._sessions: Dict[Tuple[Optional[int], int], SearchSession] = {}

    @staticmethod
    def _make_key(group_id: Optional[int], user_id: int) -> Tuple[Optional[int], int]:
        return (group_id, user_id)

    def set_search_results(self, group_id: Optional[int], user_id: int, results: List[ComicInfo]):
        """
        为指定用户存储搜索结果，创建或覆盖会话。
        group_id 为 None 时表示私聊。
        """
        key = self._make_key(group_id, user_id)
        self._sessions[key] = SearchSession(results, group_id, user_id)

    def get_search_results(self, group_id: Optional[int], user_id: int) -> Optional[List[ComicInfo]]:
        """
        获取指定用户的搜索结果。
        如果会话不存在或已过期，返回 None。
        """
        key = self._make_key(group_id, user_id)
        session = self._sessions.get(key)
        if session is None:
            return None
        if self._is_expired(session):
            del self._sessions[key]
            return None
        return session.results

    def is_active(self, group_id: Optional[int], user_id: int) -> bool:
        """
        检查指定用户是否有活跃的搜索会话（存在且未过期）。
        """
        key = self._make_key(group_id, user_id)
        session = self._sessions.get(key)
        if session is None:
            return False
        if self._is_expired(session):
            del self._sessions[key]
            return False
        return True

    def clear_search_results(self, group_id: Optional[int], user_id: int):
        """
        清除指定用户的搜索会话。
        """
        key = self._make_key(group_id, user_id)
        if key in self._sessions:
            del self._sessions[key]

    def _is_expired(self, session: SearchSession) -> bool:
        return (time.time() - session.created_at) > self.SESSION_TIMEOUT

    def cleanup_expired(self):
        """
        清理所有已过期的会话。可由定时任务调用。
        """
        expired_keys = [k for k, s in self._sessions.items() if self._is_expired(s)]
        for k in expired_keys:
            del self._sessions[k]
