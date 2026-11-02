# plugins/interactive_help/config.py
"""帮助菜单配置加载与管理。"""

import os
from pathlib import Path

import yaml
from nonebot.log import logger

from ._models import HelpMenuRootConfig

PLUGIN_DIR = Path(__file__).parent
DEFAULT_CONFIG_PATH = PLUGIN_DIR / "data" / "help_menu.yaml"

# 是否使用 json 卡片渲染帮助菜单。
# 默认关闭：个人号协议端（NapCat / Lagrange）不渲染 json 卡片，只会显示占位文本；
# 官方渠道机器人可设 HELP_USE_CARD=true 开启卡片外观。
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_use_card() -> bool:
    return os.getenv("HELP_USE_CARD", "false").strip().lower() in _TRUE_VALUES


class ConfigManager:
    """帮助菜单配置管理器，支持热重载。"""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._config: HelpMenuRootConfig | None = None
        self.reload()

    def reload(self) -> HelpMenuRootConfig:
        """重新加载 YAML 配置文件。"""
        if not self.config_path.exists():
            logger.warning(f"帮助菜单配置文件不存在: {self.config_path}，将使用默认配置。")
            self._config = HelpMenuRootConfig()
            return self._config

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            self._config = HelpMenuRootConfig.model_validate(raw)
            logger.info(f"帮助菜单配置已加载: {self.config_path}")
        except Exception as e:
            logger.error(f"加载帮助菜单配置失败: {e}")
            self._config = HelpMenuRootConfig()

        return self._config

    @property
    def config(self) -> HelpMenuRootConfig:
        if self._config is None:
            self.reload()
        return self._config

    @property
    def menu(self):
        return self.config.menu

    @property
    def permissions(self):
        return self.config.permissions

    @property
    def use_card(self) -> bool:
        """是否用 json 卡片渲染（默认 False，走纯文本）。"""
        return _env_use_card()


# 模块级单例，插件加载时初始化
config_manager = ConfigManager()


def reload_config() -> HelpMenuRootConfig:
    """供命令调用，热重载配置。"""
    return config_manager.reload()
