"""ai_config_console - 人格文件读写。

管理 group_prompts/private_prompts 目录下的 .txt 人格文件。
- 列表：按场景列出文件名、大小、修改时间
- 读：返回内容
- 写：新建/覆盖（校验文件名白名单 + 长度上限）
- 删：删除文件（删除前备份）
"""

import re
from datetime import datetime
from pathlib import Path

from ._config_store import CONFIG_DIR, BACKUP_ROOT
from ._models import NAME_PATTERN, PROMPT_MAX_LENGTH, SCENES

PROMPT_DIRS = {
    "group": CONFIG_DIR / "group_prompts",
    "private": CONFIG_DIR / "private_prompts",
}


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


def _validate_content(content: str) -> str:
    content = content.strip()
    if not content:
        raise ValueError("人格内容不能为空")
    if len(content) > PROMPT_MAX_LENGTH:
        raise ValueError(f"人格内容超过 {PROMPT_MAX_LENGTH} 字上限")
    return content


def _file_path(scene: str, name: str) -> Path:
    _validate_name(name)
    d = _scene_dir(scene)
    p = d / f"{name}.txt"
    return p


def _backup_prompt(scene: str, name: str) -> Path | None:
    """删除前备份人格文件到备份目录（仅当文件存在）。"""
    src = _file_path(scene, name)
    if not src.is_file():
        return None
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_ROOT / f"prompt_{scene}_{name}_{ts}.txt"
    dest.write_bytes(src.read_bytes())
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
    _validate_content(content)
    p = _file_path(scene, name)
    p.write_text(content, encoding="utf-8")


def delete_prompt(scene: str, name: str) -> None:
    _backup_prompt(scene, name)
    p = _file_path(scene, name)
    if p.is_file():
        p.unlink()
