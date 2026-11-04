"""借用 suggarchat 的人格，给 KP 叙事与 NPC 台词加一点“性格”。

数据来源（只读，不改 suggarchat 的任何东西）：
- 配置：``%APPDATA%/nonebot2/onebot_plugin_suggarchat/config.toml``
  里的 ``group_prompt_character`` / ``private_prompt_character``
- 人格：同目录 ``group_prompts/<name>.txt`` / ``private_prompts/<name>.txt``

用法上只取一段「语气简介」进 prompt，并明确告诉模型：借语气，不借身份，
守秘人的职责（不剧透、不替玩家决定、不写规则）不变。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

MAX_BRIEF = 280

_GROUP_KEY = "group_prompt_character"
_PRIVATE_KEY = "private_prompt_character"


@dataclass(frozen=True)
class Persona:
    name: str
    brief: str


def config_dir() -> Path:
    appdata = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "nonebot2" / "onebot_plugin_suggarchat"


def _read_character(scene: str) -> str:
    key = _GROUP_KEY if scene == "group" else _PRIVATE_KEY
    cfg = config_dir() / "config.toml"
    if not cfg.is_file():
        return ""
    pattern = re.compile(rf'^\s*{key}\s*=\s*"([^"]*)"\s*$')
    for line in cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1).strip()
    return ""


def persona_root() -> Path:
    """人格目录：默认跟 suggarchat 一致，可用 COC_PERSONA_DIR 覆盖。"""
    override = os.getenv("COC_PERSONA_DIR", "").strip()
    return Path(override) if override else config_dir()


def persona_path(scene: str, name: str) -> Path:
    sub = "group_prompts" if scene == "group" else "private_prompts"
    return persona_root() / sub / f"{name}.txt"


def extract_brief(text: str, limit: int = MAX_BRIEF) -> str:
    """把人格文件压成一段语气简介（去掉标题符号、换行，截断）。"""
    cleaned = re.sub(r"[#*`>]+", "", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit]


def load_persona(scene: str, mode: str | None = None) -> Persona | None:
    """按模式加载人格。

    mode:
      - ``off``：不用人格
      - ``auto``（默认）：读 suggarchat 当前配置的人格名
      - 其他任意字符串：当作人格文件名
    """
    mode = (mode if mode is not None else os.getenv("COC_PERSONA_MODE", "auto")).strip()
    if mode.lower() == "off":
        return None
    name = _read_character(scene) if mode.lower() in ("", "auto") else mode
    if not name:
        # 配置读不到时（例如被沙箱隔离），允许用环境变量显式指定人格名
        name = os.getenv("COC_PERSONA_NAME", "").strip()
    if not name:
        return None
    path = persona_path(scene, name)
    if not path.is_file():
        return None
    brief = extract_brief(path.read_text(encoding="utf-8", errors="ignore"))
    if not brief:
        return None
    return Persona(name=name, brief=brief)
