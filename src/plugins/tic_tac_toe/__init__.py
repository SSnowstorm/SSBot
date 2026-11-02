"""tic_tac_toe - 井字棋插件入口。

原实现为空壳且 bot.py 未加载（D-05）；这里显式导入命令模块完成 matcher 注册，
bot.py 用 `nonebot.load_plugin("src.plugins.tic_tac_toe")` 加载本包。
"""

from . import tic_tac_toe  # noqa: F401  导入即注册 matcher

__all__ = []
