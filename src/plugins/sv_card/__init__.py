# plugins/sv_card/__init__.py
"""影之诗：超凡世界 查卡器插件。

使用方法：
    /sv <关键词>       模糊搜索卡片
    /sv <卡名>         精确匹配单卡
    /sv #<职业>        按职业过滤（如 #剑 #森林）
    /sv !<ID>          按卡牌ID精确查询
    /sv_reload         重新加载卡牌数据

数据来源：
    - 英文数据：ParticleG/shadowverse-wb-db (cards.json)
    - 中文支持：通过旅法师营地API或本地中文数据

设计说明：
- 启动时加载卡牌数据到内存缓存
- 支持多级模糊匹配（前缀 > 包含 > 技能描述）
- 卡片图片发送前转换为QQ兼容格式
"""

# 导入 handler 以注册 matcher
from . import _handler  # noqa: F401
from ._cache import card_cache

# 注意：不要在模块级别调用 logger.info()，因为这会在 nonebot 初始化前执行
