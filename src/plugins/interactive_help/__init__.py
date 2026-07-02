# plugins/interactive_help/__init__.py
"""交互式帮助菜单插件。

使用方法：
    /help           触发主菜单（发送 json 卡片）
    /help <分类名>   触发子菜单
    /help_reload     热重载菜单配置（需管理员权限）

设计说明：
- 菜单内容通过 YAML 配置控制，方便扩展。
- 权限体系与 NoneBot SUPERUSERS 联动，预留管理员/VIP/黑名单。
- 当前使用 json 消息段发送卡片外观（仅展示，不支持按钮交互）。
- 后续若切换到 QQ 官方适配器，可改用 ark + keyboard 实现完整交互。
"""

from nonebot.log import logger

# 导入 handler 以注册 matcher
from . import _handler  # noqa: F401
from ._config import config_manager

logger.info("交互式帮助菜单插件已加载。")
