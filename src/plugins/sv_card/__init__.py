# plugins/sv_card/__init__.py
"""影之诗：超凡世界 查卡器插件。

使用方法：
    /sv <关键词>       模糊搜索卡片
    /sv <卡名>         精确匹配单卡
    /sv #<职业>        按职业过滤（如 #精灵 #皇家）
    /sv !<ID>          按卡牌ID精确查询
    /sv <ID>           直接输入7-8位ID也可查询（不加!也行）
    /sv_reload         重新加载卡牌数据

数据来源：
    - src/plugins/sv_card/data/cards_cn_translated.json（本地中文翻译数据）
    - 用户自制 5 层规则翻译引擎产出（术语词典 + 句式模式 + 短语词典 + 语法变形 + 片假名音译）
    - 共 735 张卡牌（v3 翻译版本，2026-07-03）

数据特点：
    - name 翻译率 88.3%，skill_text 翻译率 50.6% + 18.2% 轻度残留（基本可读）
    - 残留假名时会附日文原文对照
    - flavour_text 翻译质量差，暂不展示
    - class 从 card_id[3] 推断（0=中立/1=精灵/2=皇家/3=法师/4=龙族/5=梦魇/6=主教/7=超越者）

设计说明：
- 启动时加载卡牌数据到内存缓存（异步线程读取 JSON）
- 支持多级模糊匹配（前缀 > 包含 > 技能描述）
- 卡片图片发送前转换为QQ兼容格式
"""

# 导入 handler 以注册 matcher
from . import _handler  # noqa: F401
from ._cache import card_cache

# 注意：不要在模块级别调用 logger.info()，因为这会在 nonebot 初始化前执行
