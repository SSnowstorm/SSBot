# plugins/sv_card/_config.py
"""影之诗超凡世界 插件配置。

配置项：
    - 数据源URL
    - 缓存策略
    - 图片格式
"""

from typing import Optional
from pydantic import BaseModel


class SVCardConfig(BaseModel):
    """影之诗查卡器配置。"""

    # 英文数据源URL
    en_cards_url: str = "https://raw.githubusercontent.com/ParticleG/shadowverse-wb-db/main/cards.json"

    # 中文数据源路径（本地 JSON）
    chs_cards_path: str = "src/plugins/sv_card/data/cards_cn_translated.json"

    # 缓存过期时间（小时）
    cache_expire_hours: int = 24

    # 搜索结果最大数量
    search_result_limit: int = 10

    # 图片格式（png/webp/jpg）
    image_format: str = "png"

    # 是否启用图片下载缓存
    enable_image_cache: bool = True

    # 图片缓存目录
    image_cache_dir: str = "data/sv_card/images"

    # 默认语言（en/chs/cht/ja/ko）
    default_lang: str = "en"

    # 是否自动加载数据（启动时）
    auto_load_on_startup: bool = True

    # 职业名称映射（中文到代码）
    # card_id[3] → 职业代码（0=中立/1=精灵/2=皇家/3=法师/4=龙族/5=梦魇/6=主教/7=超越者）
    # 注意：SV2 将原版死灵+吸血鬼合并为深渊（中文"梦魇"）
    class_name_map: dict[str, str] = {
        "中立": "0",
        "精灵": "1",
        "皇家": "2",
        "法师": "3",
        "龙族": "4",
        "梦魇": "5",
        "主教": "6",
        "超越者": "7",
    }


# 全局配置实例
sv_card_config = SVCardConfig()
