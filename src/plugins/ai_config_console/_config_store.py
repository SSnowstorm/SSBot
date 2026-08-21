"""ai_config_console - config.toml 读写。

核心职责：
- 读取 suggarchat 的 config.toml（TOML 解析）
- 按分组输出（api_key 打码）
- 保存：备份 → 原子写（tmp + os.replace）→ 触发 UniConfig 热重载
- 只更新"可编辑"字段，未渲染分组原样保留
"""

import os
import shutil
import tomllib
import tomli_w
from datetime import datetime
from pathlib import Path

from ._models import SCENES

# 配置文件位置（UniConfig 目录）
CONFIG_DIR = Path.home() / "AppData" / "Roaming" / "nonebot2" / "nonebot_plugin_suggarchat"
CONFIG_PATH = CONFIG_DIR / "config.toml"

# 备份目录（项目 data 下）
BACKUP_ROOT = Path(__file__).resolve().parents[3] / "data" / "ai_config_console" / "backups"
BACKUP_KEEP = 10

# 可编辑分组 → config.toml 中的 TOML 段映射
# key: API 分组名, value: (TOML 段, 可编辑字段白名单, None=整段可编辑)
EDITABLE_MAP = {
    "basic": (None, {"enable", "parse_segments", "group_prompt_character",
                     "private_prompt_character"}),
    "model": ("default_preset", {"model", "base_url"}),
    "admin": ("admin", {"admins", "admin_group", "allow_send_to_admin"}),
    "session": ("session", None),
    "autoreply": ("autoreply", None),
    "function": ("function", {"chat_pending_mode", "synthesize_forward_message",
                              "nature_chat_style", "poke_reply", "enable_group_chat",
                              "enable_private_chat", "allow_custom_prompt",
                              "use_user_nickname"}),
    "llm": ("llm_config", {"stream", "memory_lenth_limit", "max_tokens",
                           "enable_tokens_limit", "llm_timeout", "auto_retry",
                           "max_retries", "enable_memory_abstract",
                           "memory_abstract_proportion", "block_msg"}),
    "tools": ("llm_config.tools", {"enable_tools", "use_minimal_context", "enable_report",
                                   "report_exclude_system_prompt", "report_exclude_context",
                                   "report_then_block", "report_invoke_level",
                                   "agent_mode_enable"}),
    "usage_limit": ("usage_limit", None),
}


def _load_toml() -> dict:
    """读取 config.toml，返回 dict。文件缺失/解析失败抛异常。"""
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def _get_section(data: dict, dotted: str | None) -> dict:
    """按点分路径取 TOML 段（如 llm_config.tools）。"""
    if not dotted:
        return data
    cur = data
    for part in dotted.split("."):
        cur = cur[part]
    return cur


def _set_section(data: dict, dotted: str, value: dict) -> None:
    """按点分路径写入 TOML 段（不存在则创建）。"""
    parts = dotted.split(".")
    cur = data
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def mask_api_key(key: str) -> str:
    """API key 打码：sk-****后4位。"""
    if not key:
        return ""
    key = key.strip()
    if len(key) <= 8:
        return "****"
    return key[:3] + "****" + key[-4:]


def get_config() -> dict:
    """读取全量配置，按 API 分组返回（api_key 打码，只读字段标注）。"""
    data = _load_toml()

    # 只读字段（返回但标注 editable: false）
    read_only = {
        "basic": {"matcher_function", "preset"},
        "model": {"api_key", "protocol", "thought_chain_model", "multimodal"},
    }

    result: dict = {}
    for group, (section, whitelist) in EDITABLE_MAP.items():
        src = _get_section(data, section) if section else data
        editable = whitelist if whitelist is not None else set(src.keys())
        ro = read_only.get(group, set())
        result[group] = {}
        for k, v in src.items():
            if k in ro:
                # 打码 + 只读
                if k == "api_key":
                    result[group][k] = {"value": mask_api_key(v), "editable": False}
                else:
                    result[group][k] = {"value": v, "editable": False}
            elif k in editable:
                result[group][k] = {"value": v, "editable": True}
            # 不在白名单的字段不返回（未渲染组）
    return result


def backup_config() -> Path:
    """备份 config.toml 到备份目录，保留最近 BACKUP_KEEP 份，返回备份路径。"""
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_ROOT / f"config_{ts}.toml"
    shutil.copy2(CONFIG_PATH, dest)
    # 清理超出保留数的旧备份
    backups = sorted(BACKUP_ROOT.glob("config_*.toml"))
    for old in backups[:-BACKUP_KEEP]:
        old.unlink(missing_ok=True)
    return dest


def list_backups() -> list[dict]:
    """列出 config.toml 备份文件（最近 BACKUP_KEEP 份，按时间倒序）。"""
    if not BACKUP_ROOT.is_dir():
        return []
    items = []
    for f in BACKUP_ROOT.glob("config_*.toml"):
        stat = f.stat()
        items.append({
            "name": f.name,
            "size": stat.st_size,
            "updated": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    items.sort(key=lambda x: x["updated"], reverse=True)
    return items[:BACKUP_KEEP]


def update_config(req_groups: dict) -> Path:
    """保存配置（部分更新）。

    仅更新 EDITABLE_MAP 白名单内的字段；备份后原子写。
    返回备份路径。
    """
    data = _load_toml()

    for group, payload in req_groups.items():
        if group not in EDITABLE_MAP:
            continue
        section, whitelist = EDITABLE_MAP[group]
        if section is None:
            target = data
        else:
            # 目标段可能不存在（首次），取或建
            parts = section.split(".")
            cur = data
            for part in parts:
                cur = cur.setdefault(part, {})
            target = cur

        for k, v in payload.items():
            if whitelist is not None and k not in whitelist:
                continue
            # 跳过敏感字段，前端永远传不回明文 api_key
            if k == "api_key":
                continue
            target[k] = v

    # 备份
    backup_path = backup_config()

    # 原子写：tmp + os.replace
    tmp_path = CONFIG_PATH.with_suffix(".toml.tmp")
    with open(tmp_path, "wb") as f:
        tomli_w.dump(data, f)
    os.replace(tmp_path, CONFIG_PATH)

    return backup_path
