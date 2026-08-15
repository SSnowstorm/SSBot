# plugins/sv_card/_cache.py
"""影之诗超凡世界 卡牌数据缓存管理。

功能：
    - 启动时从本地 JSON 文件加载中文卡牌数据（用户自制翻译版）
    - 按 ID 查询单卡
    - 按名称/技能模糊搜索
    - 定期或手动刷新缓存
    - 根据 card_set_id 推断职业

数据源：
    src/plugins/sv_card/data/cards_cn_translated.json
    （用户自制的 5 层规则翻译引擎产出，共 735 张卡，v3 版本）

字段映射（用户数据 → 内部表示）：
    card_id   → id
    name      → name
    clan      → 缺省，恒 None。从 card_id[3] 推断后填到 class_code / class_name
    card_set_id → 10000-10008 卡包系列（与 card_id[2] 对应，不用于推断职业）
    type (int 1-4) → type_str
    rarity (int 1-4) → 已有映射
    skill_text / skill_text_ja
    flavour_text / flavour_text_ja（不展示，仅保留供扩展）
    evo_skill_text 恒空（进化效果内嵌在 skill_text 的 <ev>/<sev> 标签中）
    base_card_image_id 恒空（用 card_id 拼 URL 兜底）
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import zhconv

# 注意：logger 在首次使用时才导入，避免在 NoneBot 初始化前导入


def _get_logger():
    """延迟获取 logger 实例。"""
    from nonebot.log import logger
    return logger


# ============== 配置常量 ==============

# 中文卡牌数据文件（用户自制翻译版，已移至插件内部 data 目录）
CHS_CARDS_FILE = Path(__file__).parent / "data" / "cards_cn_translated.json"

# 缓存有效期（小时）
CACHE_EXPIRE_HOURS = 24

# ============== 职业 / 卡包 映射 ==============

# set_id → 卡包系列名（仅参考，不用于推断职业）
# set_id 和 card_id[2] 一一对应：set 10000→[2]=0, 10001→[2]=1, ... 10008→[2]=8
# 注意：set_id 是"卡包系列"而非职业，同一 set 内包含所有职业的卡
SET_ID_TO_PACK_NAME = {
    10000: "中立基础包",
    10001: "精灵包",
    10002: "皇家包",
    10003: "法师包",
    10004: "龙族包",
    10005: "梦魇包",
    10006: "主教包",
    10007: "超越者包",
    10008: "扩展包",
}

# card_id[3] 位 → 职业名（权威映射）
# card_id 编码（8 位）：1 0 S C N N N N
#   [0]    = 固定 '1'
#   [1]    = 固定 '0'
#   [2]    = 卡包系列号（0-8，对应 set_id 末位）
#   [3]    = 职业代码（0=中立, 1=精灵, 2=皇家, 3=法师, 4=龙族, 5=梦魇, 6=主教, 7=超越者）
#   [4-7]  = 卡牌编号
#
# 验证来源：shadowverse.gg 卡牌列表 + 卡牌名称交叉确认
#   10011110 [3]=1 → Fairy Tamer（精灵）
#   10021110 [3]=2 → Arms Peddler（皇家）
#   10031110 [3]=3 → Witch's New Brew（法师）
#   10041110 [3]=4 → Axe-Wielding Dragonslayer（龙族）
#   10051110 [3]=5 → Night Fiend（梦魇）
#   10061110 [3]=6 → Fox of Purity（主教）
#   10071110 [3]=7 → Puppet Lancer（超越者）
PROFESSION_CODE_TO_NAME = {
    "0": "中立",
    "1": "精灵",
    "2": "皇家",
    "3": "法师",
    "4": "龙族",
    "5": "梦魇",
    "6": "主教",
    "7": "超越者",
}

# 内部职业代码（沿用 0-7）
CLASS_CODE_TO_NAME = {
    "0": "中立",
    "1": "精灵",
    "2": "皇家",
    "3": "法师",
    "4": "龙族",
    "5": "梦魇",
    "6": "主教",
    "7": "超越者",
}

CLASS_NAME_TO_CODE = {v: k for k, v in CLASS_CODE_TO_NAME.items()}
# 兼容更多职业别名
_CLASS_ALIAS = {
    "中立": "0", "neutral": "0",
    "精灵": "1", "森林": "1", "妖精": "1", "elf": "1", "forest": "1",
    "皇家": "2", "剑": "2", "剑士": "2", "皇家护卫": "2", "sword": "2", "royal": "2",
    "法师": "3", "巫师": "3", "魔女": "3", "rune": "3", "witch": "3",
    "龙族": "4", "龙": "4", "dragon": "4",
    "梦魇": "5", "死": "5", "死灵": "5", "深渊": "5", "abyss": "5", "shadow": "5", "vampire": "5",
    "主教": "6", "教会": "6", "圣堂": "6", "haven": "6", "bishop": "6",
    "超越者": "7", "魂": "7", "复仇": "7", "复仇者": "7", "人偶": "7", "portal": "7", "nemesis": "7",
}
CLASS_NAME_TO_CODE.update(_CLASS_ALIAS)

# ============== 稀有度映射 ==============

RARITY_CODE_TO_NAME = {
    "1": "铜",
    "2": "银",
    "3": "金",
    "4": "虹",
}

# ============== 类型映射 ==============

# 用户数据里 type 是 int（1=随从 2=法术 3=护符 4=纹章）
TYPE_INT_TO_NAME = {
    1: "随从",
    2: "法术",
    3: "护符",
    4: "纹章",
}

# 日文假名正则（用于检测翻译残留）
_KANA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")


def _infer_class_info(card_id_str: str, card_set_id: int) -> tuple[str, str]:
    """根据 card_id 推断职业 (代码, 中文名)。

    card_id 编码（8 位数字）：
        [0]    = 固定 '1'
        [1]    = 固定 '0'
        [2]    = 卡包系列号（0-8，对应 set_id 末位，不是职业代码）
        [3]    = 职业代码（0=中立, 1=精灵, 2=皇家, 3=法师, 4=龙族, 5=梦魇, 6=主教, 7=超越者）
        [4-7]  = 卡牌编号

    card_set_id 是另一维度的"卡包系列"（10000-10008），与 card_id[2] 一一对应，
    但同一 set 内包含所有职业的卡牌，因此不能用它推断职业。

    Returns:
        (class_code, class_name)
    """
    if len(card_id_str) >= 4:
        prof_code = card_id_str[3]
        if prof_code in PROFESSION_CODE_TO_NAME:
            return (prof_code, PROFESSION_CODE_TO_NAME[prof_code])
    return ("0", "中立")


def _normalize_card(raw: dict) -> dict:
    """把用户数据的原始卡牌转换为内部统一格式。

    内部字段约定：
        id, name (简体), name_raw (原始繁简混用), name_ja,
        class_code, class_name, type, type_name, rarity, rarity_name,
        cost, atk, life,
        skill_text, skill_text_ja, evo_skill_text, flavour_text, flavour_text_ja,
        cv, illustrator, tribes, card_set_id, base_card_image_id,
        skill_has_kana (bool),  # 标记 skill_text 是否含假名

    注意：name 字段经 zhconv 繁→简转换，name_raw 保留原始数据供参考。
    """
    card_id_raw = raw.get("card_id", raw.get("id", ""))
    # 用户数据里 card_id 是数字，索引时统一转 str
    card_id_str = str(card_id_raw)
    # 补 0 到 8 位（与原格式一致）
    if len(card_id_str) < 8:
        card_id_str = card_id_str.zfill(8)

    card_set_id = raw.get("card_set_id", 10000)
    class_code, class_name = _infer_class_info(card_id_str, card_set_id)

    type_int = raw.get("type", 0)
    type_name = TYPE_INT_TO_NAME.get(type_int, "未知")

    rarity_int = raw.get("rarity", 1)
    rarity_name = RARITY_CODE_TO_NAME.get(str(rarity_int), "铜")

    skill_text = raw.get("skill_text", "") or ""
    skill_text_ja = raw.get("skill_text_ja", "") or ""
    skill_has_kana = bool(_KANA_RE.search(skill_text)) and bool(skill_text)

    # 卡名繁→简转换（数据源由翻译引擎产出，存在繁简混用如「天宮」→「天宫」）
    raw_name = raw.get("name", "") or ""
    name_cn = zhconv.convert(raw_name, "zh-cn") if raw_name else ""

    return {
        "id": card_id_str,
        "name": name_cn,
        "name_raw": raw_name,
        "name_ja": raw.get("name_ja", "") or "",
        "class_code": class_code,
        "class_name": class_name,
        "type": type_int,
        "type_name": type_name,
        "rarity": rarity_int,
        "rarity_name": rarity_name,
        "cost": raw.get("cost", 0),
        "atk": raw.get("atk", 0),
        "life": raw.get("life", 0),
        "skill_text": skill_text,
        "skill_text_ja": skill_text_ja,
        "evo_skill_text": raw.get("evo_skill_text", "") or "",
        "flavour_text": raw.get("flavour_text", "") or "",
        "flavour_text_ja": raw.get("flavour_text_ja", "") or "",
        "cv": raw.get("cv", "") or "",
        "illustrator": raw.get("illustrator", "") or "",
        "tribes": raw.get("tribes", []) or [],
        "card_set_id": card_set_id,
        "base_card_image_id": raw.get("base_card_image_id", "") or "",
        "skill_has_kana": skill_has_kana,
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
        self._source_path: Optional[str] = None

    async def load_cards(self, force: bool = False) -> bool:
        """从本地 JSON 文件加载卡牌数据。

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
                    _get_logger().info(
                        f"卡牌缓存仍有效（已更新于 {self._last_update}），跳过加载。"
                    )
                    return True
            else:
                return True

        _get_logger().info(f"正在从 {CHS_CARDS_FILE} 加载卡牌数据...")

        # 在线程池中读取文件，避免阻塞事件循环
        loop = asyncio.get_running_loop()
        try:
            raw_data = await loop.run_in_executor(None, _read_chs_file, CHS_CARDS_FILE)
        except FileNotFoundError:
            _get_logger().error(f"❌ 卡牌数据文件不存在: {CHS_CARDS_FILE}")
            return False
        except json.JSONDecodeError as e:
            _get_logger().error(f"❌ JSON 解析失败: {e}")
            return False
        except Exception as e:
            _get_logger().error(f"❌ 加载卡牌数据失败: {e}")
            return False

        # 过滤 _meta，转换格式
        self._cards = []
        for k, v in raw_data.items():
            if k == "_meta":
                continue
            if not isinstance(v, dict):
                continue
            self._cards.append(_normalize_card(v))

        # 构建索引
        self._build_indexes()

        self._last_update = datetime.now()
        self._is_loaded = True
        self._source_path = str(CHS_CARDS_FILE)

        _get_logger().info(
            f"✅ 成功加载 {len(self._cards)} 张卡牌（来源：{self._source_path}）。"
        )
        return True

    def _build_indexes(self):
        """构建搜索索引。"""
        self._cards_by_id = {}
        self._cards_by_name = {}

        for card in self._cards:
            # 按 ID 索引
            cid = card.get("id", "")
            if cid:
                self._cards_by_id[cid] = card

            # 按名称索引（中文优先，同时索引日文用于跨语种搜索）
            name_cn = (card.get("name") or "").lower()
            if name_cn:
                self._cards_by_name.setdefault(name_cn, []).append(card)
            name_ja = (card.get("name_ja") or "").lower()
            if name_ja and name_ja != name_cn:
                self._cards_by_name.setdefault(name_ja, []).append(card)

    def get_all_cards(self) -> list[dict]:
        """获取所有卡牌。"""
        return self._cards

    def get_card_by_id(self, card_id: str) -> Optional[dict]:
        """根据 ID 获取单张卡牌（支持不带前导 0 的查询）。"""
        cid = str(card_id).zfill(8) if str(card_id).isdigit() else str(card_id)
        return self._cards_by_id.get(cid)

    def get_cards_by_name(self, name: str) -> list[dict]:
        """根据名称获取卡牌（精确匹配）。"""
        return self._cards_by_name.get(name.lower(), [])

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    @property
    def last_update(self) -> Optional[datetime]:
        return self._last_update

    @property
    def card_count(self) -> int:
        return len(self._cards)

    @property
    def source_path(self) -> Optional[str]:
        return self._source_path


# ============== 文件读取 ==============

def _read_chs_file(path: Path) -> dict:
    """同步读取 JSON 文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============== 全局缓存实例 ==============

card_cache = CardCache()


# ============== 便捷函数 ==============

async def reload_cards() -> bool:
    """强制重新加载卡牌数据。"""
    return await card_cache.load_cards(force=True)


# ============== 启动时加载 ==============

async def init_cache():
    """初始化卡牌缓存（在 Bot 启动时调用）。"""
    await card_cache.load_cards()


# ============== 定时任务（可选） ==============

def _try_register_scheduler():
    """尝试注册定时任务（scheduler 插件可选）。"""
    try:
        from nonebot import get_loaded_plugins
        # nonebot 2.5 已移除 get_plugin_list()，改用 get_loaded_plugins()（返回 Plugin 对象）
        plugin_names = {p.name.replace("-", "_") for p in get_loaded_plugins()}
        if "nonebot_plugin_scheduler" not in plugin_names:
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
