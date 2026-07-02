# plugins/sv_card/_cache.py
"""影之诗超凡世界 卡牌数据缓存管理。

功能：
    - 启动时从GitHub加载卡牌数据
    - 按ID查询单卡
    - 按名称/技能模糊搜索
    - 定期或手动刷新缓存
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

import httpx

# 注意：logger 在首次使用时才导入，避免在 NoneBot 初始化前导入


def _get_logger():
    """延迟获取 logger 实例。"""
    from nonebot.log import logger
    return logger

# ============== 配置常量 ==============

# 英文卡牌数据源（ParticleG/shadowverse-wb-db）
EN_CARDS_URL = "https://raw.githubusercontent.com/ParticleG/shadowverse-wb-db/main/cards.json"

# 中文名称映射URL（预留，后期可扩展）
# CHS_CARDS_URL = "https://example.com/shadowverse/cards_chs.json"

# 缓存有效期（小时）
CACHE_EXPIRE_HOURS = 24

# ============== 职业代码映射 ==============

CLASS_CODE_TO_NAME = {
    "0": "中立",
    "1": "森林",
    "2": "剑",
    "3": "龙",
    "4": "龙",
    "5": "死",
    "6": "主教",
    "7": "魂",
}

CLASS_NAME_TO_CODE = {v: k for k, v in CLASS_CODE_TO_NAME.items()}
# 添加英文职业名映射
CLASS_NAME_TO_CODE.update({
    "neutral": "0",
    "forest": "1",
    "sword": "2",
    "rune": "3",
    "dragon": "4",
    "abyss": "5",
    "haven": "6",
    "portal": "7",
})

# ============== 稀有度映射 ==============

RARITY_CODE_TO_NAME = {
    "1": "铜",
    "2": "银",
    "3": "金",
    "4": "虹",
}

# ============== 数据缓存类 ==============

class CardCache:
    """卡牌数据缓存管理器。"""

    def __init__(self):
        self._cards: list[dict] = []
        self._cards_by_id: dict[str, dict] = {}
        self._cards_by_name: dict[str, list[dict]] = {}
        self._last_update: Optional[datetime] = None
        self._is_loaded = False

    async def load_cards(self, force: bool = False) -> bool:
        """从GitHub加载卡牌数据。

        Args:
            force: 是否强制重新加载

        Returns:
            bool: 加载是否成功
        """
        if self._is_loaded and not force:
            if self._last_update:
                hours_since_update = (
                    datetime.now() - self._last_update
                ).total_seconds() / 3600
                if hours_since_update < CACHE_EXPIRE_HOURS:
                    _get_logger().info(f"卡牌缓存仍有效（已更新于 {self._last_update}），跳过加载。")
                    return True
            else:
                return True

        _get_logger().info("正在从GitHub加载卡牌数据...")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(EN_CARDS_URL)
                response.raise_for_status()
                data = response.json()

            # 处理数据
            if isinstance(data, list):
                self._cards = data
            elif isinstance(data, dict) and "cards" in data:
                self._cards = data["cards"]
            else:
                _get_logger().error(f"未知的卡片数据格式: {type(data)}")
                return False

            # 构建索引
            self._build_indexes()

            self._last_update = datetime.now()
            self._is_loaded = True

            _get_logger().info(f"✅ 成功加载 {len(self._cards)} 张卡牌。")
            return True

        except httpx.HTTPError as e:
            _get_logger().error(f"HTTP错误: {e}")
            return False
        except json.JSONDecodeError as e:
            _get_logger().error(f"JSON解析错误: {e}")
            return False
        except Exception as e:
            _get_logger().error(f"加载卡牌数据失败: {e}")
            return False

    def _build_indexes(self):
        """构建搜索索引。"""
        self._cards_by_id = {}
        self._cards_by_name = {}

        for card in self._cards:
            # 按ID索引
            card_id = card.get("id", "")
            if card_id:
                self._cards_by_id[str(card_id)] = card

            # 按名称索引（支持大小写不敏感搜索）
            name = card.get("name", "")
            if name:
                name_lower = name.lower()
                if name_lower not in self._cards_by_name:
                    self._cards_by_name[name_lower] = []
                self._cards_by_name[name_lower].append(card)

    def get_all_cards(self) -> list[dict]:
        """获取所有卡牌。"""
        return self._cards

    def get_card_by_id(self, card_id: str) -> Optional[dict]:
        """根据ID获取单张卡牌。"""
        return self._cards_by_id.get(str(card_id))

    def get_cards_by_name(self, name: str) -> list[dict]:
        """根据名称获取卡牌（精确匹配）。"""
        return self._cards_by_name.get(name.lower(), [])

    @property
    def is_loaded(self) -> bool:
        """检查缓存是否已加载。"""
        return self._is_loaded

    @property
    def last_update(self) -> Optional[datetime]:
        """获取最后更新时间。"""
        return self._last_update

    @property
    def card_count(self) -> int:
        """获取缓存的卡牌数量。"""
        return len(self._cards)


# ============== 全局缓存实例 ==============

card_cache = CardCache()


# ============== 便捷函数 ==============

async def reload_cards() -> bool:
    """强制重新加载卡牌数据。"""
    return await card_cache.load_cards(force=True)


# ============== 启动时加载 ==============

async def init_cache():
    """初始化卡牌缓存（在Bot启动时调用）。"""
    await card_cache.load_cards()


# ============== 定时任务（可选，需要 nonebot-plugin-scheduler） ==============
# 注意：不强制依赖 scheduler，如有需要请手动安装：
# pip install nonebot-plugin-scheduler
# 并在 pyproject.toml 中添加 nonebot-plugin-scheduler

def _try_register_scheduler():
    """尝试注册定时任务（scheduler 插件可选）。"""
    try:
        # 先检查插件是否已安装，避免 require 内部的 ERROR 日志
        import nonebot
        plugin_list = nonebot.get_plugin_list()
        if "nonebot-plugin-scheduler" not in plugin_list:
            _get_logger().debug("nonebot-plugin-scheduler 未安装，跳过定时任务")
            return

        from nonebot import require
        scheduler = require("nonebot-plugin-scheduler")
        @scheduler.scheduled_job("interval", hours=CACHE_EXPIRE_HOURS)
        async def _refresh_cache():
            _get_logger().info("定时刷新影之诗卡牌数据...")
            await card_cache.load_cards(force=True)
        _get_logger().info("定时任务注册成功（每24小时刷新一次）")
    except Exception as e:
        _get_logger().debug(f"定时任务注册失败（不影响核心功能）: {e}")
