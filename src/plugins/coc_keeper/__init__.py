"""coc_keeper - AI 跑团主持人（CoC 7e）插件。

P0 范围（当前）：
- 规则内核：d100 / 奖励惩罚骰 / 检定 / 对抗 / SAN / 伤害与重伤
- 持久层：独立 SQLite（data/coc_keeper/coc.sqlite3）
- 命令层：``/coc 车卡``、``/coc 检定 <技能> [困难/极难]``、``/coc 状态``

后续阶段（见 docs/CoC跑团KP设计分析.md）：
- P1 场景状态机 + 回合调度 + 线索
- P2 模组导入流水线 + 事件溯源复盘
- P3 车卡向导 / NPC 自动扮演 / 多团

设计原则：规则写死在代码里，模型只负责叙事（见文档 1.2）。
"""

# 只有 NoneBot 已初始化时才注册 matcher；
# 这样纯规则单测（只 import domain/store）不需要启动 NoneBot。
try:
    from nonebot import get_driver

    get_driver()  # 未初始化会抛 ValueError
    from . import _commands  # noqa: F401  （导入即注册 /coc matcher）
except Exception:  # pragma: no cover - 单测环境走这里
    _commands = None  # type: ignore[assignment]

__all__ = []
