"""ai_config_console - 人格文件读写。

管理 group_prompts/private_prompts 目录下的 .txt 人格文件：
- 列表：按场景列出文件名、大小、修改时间
- 读：返回内容
- 写：新建允许空白（网页先建空文件再编辑）；覆盖已有文件禁止清空
- 删：删除文件（删除前备份）

修复记录：
- D-01 新建空白人格不再被 422 拦截（空内容只允许用于"新建"，覆盖仍拒绝）
- D-02 字数上限改为运行期调用 get_prompt_max()，AI_PROMPT_MAX_LENGTH 真正生效
- D-04 人格备份不再无限增长：每个人格保留最近 N 份 + 全目录总量上限
"""

import re
from datetime import datetime
from pathlib import Path

from ._config_store import BACKUP_ROOT, CONFIG_DIR
from ._models import NAME_PATTERN, SCENES, get_prompt_max

PROMPT_DIRS = {
    "group": CONFIG_DIR / "group_prompts",
    "private": CONFIG_DIR / "private_prompts",
}

# 备份保留策略（D-04）：每个人格保留最近 3 份，整个备份目录最多保留 100 份
PROMPT_BACKUP_KEEP = 3
PROMPT_BACKUP_KEEP_TOTAL = 100

# 人格备份文件名：prompt_{scene}_{name}_{YYYYmmdd_HHMMSS}.txt
_BACKUP_RE = re.compile(r"^prompt_(group|private)_(.+)_(\d{8}_\d{6})\.txt$")


def _scene_dir(scene: str) -> Path:
    if scene not in SCENES:
        raise ValueError(f"场景必须是 group 或 private，收到: {scene}")
    d = PROMPT_DIRS[scene]
    d.mkdir(parents=True, exist_ok=True)
    return d


def _validate_name(name: str) -> str:
    if not re.match(NAME_PATTERN, name):
        raise ValueError("人格名仅允许中文/字母/数字/下划线/连字符，1~50 字符")
    return name


def _validate_content(content: str, *, allow_empty: bool = False) -> str:
    """校验人格内容。

    Args:
        content: 原始内容（会做 strip）
        allow_empty: 是否允许空内容（仅"新建"场景为 True）

    Raises:
        ValueError: 内容为空（且不允许空）或超过运行期字数上限
    """
    content = content.strip()
    if not content and not allow_empty:
        raise ValueError("人格内容不能为空；如需清空该人格，请直接删除它")
    if len(content) > get_prompt_max():
        raise ValueError(f"人格内容超过 {get_prompt_max()} 字上限")
    return content


def _file_path(scene: str, name: str) -> Path:
    _validate_name(name)
    d = _scene_dir(scene)
    p = d / f"{name}.txt"
    return p


def _prune_prompt_backups() -> None:
    """清理人格备份（D-04）：每个人格保留最近 N 份，并限制全目录总量。"""
    if not BACKUP_ROOT.is_dir():
        return

    groups: dict[tuple[str, str], list[Path]] = {}
    for f in BACKUP_ROOT.glob("prompt_*.txt"):
        m = _BACKUP_RE.match(f.name)
        if m is None:
            continue  # 旧命名/人工放入的文件不动
        groups.setdefault((m.group(1), m.group(2)), []).append(f)

    kept: list[Path] = []
    for files in groups.values():
        # 时间戳在文件名里，字典序倒排即"从新到旧"
        files.sort(key=lambda p: p.name, reverse=True)
        kept.extend(files[:PROMPT_BACKUP_KEEP])
        for old in files[PROMPT_BACKUP_KEEP:]:
            old.unlink(missing_ok=True)

    if len(kept) > PROMPT_BACKUP_KEEP_TOTAL:
        kept.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in kept[PROMPT_BACKUP_KEEP_TOTAL:]:
            old.unlink(missing_ok=True)


def _backup_prompt(scene: str, name: str) -> Path | None:
    """删除前备份人格文件到备份目录（仅当文件存在），并触发备份清理。"""
    src = _file_path(scene, name)
    if not src.is_file():
        return None
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_ROOT / f"prompt_{scene}_{name}_{ts}.txt"
    dest.write_bytes(src.read_bytes())
    _prune_prompt_backups()
    return dest


def list_prompts(scene: str) -> list[dict]:
    d = _scene_dir(scene)
    items = []
    for f in sorted(d.glob("*.txt")):
        stat = f.stat()
        items.append({
            "name": f.stem,
            "size": stat.st_size,
            "updated": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return items


def get_prompt(scene: str, name: str) -> str:
    p = _file_path(scene, name)
    if not p.is_file():
        raise FileNotFoundError(f"人格不存在: {scene}/{name}")
    return p.read_text(encoding="utf-8")


def save_prompt(scene: str, name: str, content: str) -> None:
    """新建或覆盖人格。

    新建（文件不存在）允许空白内容；覆盖已有文件时拒绝空内容（D-01）。
    """
    p = _file_path(scene, name)
    content = _validate_content(content, allow_empty=not p.is_file())
    p.write_text(content, encoding="utf-8")


def delete_prompt(scene: str, name: str) -> None:
    _backup_prompt(scene, name)
    p = _file_path(scene, name)
    if p.is_file():
        p.unlink()
