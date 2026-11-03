"""模组（剧本）结构：加载、校验、序列化。

数据形态与设计文档 3.2 / 附录 A 一致：
    场景图（scenes）+ 线索（clues）+ NPC + 触发/结局。
运行时只读 ``player_text`` 与已发现线索，``keeper_text`` 永不进叙事提示词。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


class ModuleError(ValueError):
    """模组结构非法。"""


@dataclass
class Exit:
    to: str
    label: str = ""
    condition: dict = field(default_factory=dict)  # 例如 {"clue": "clue_letter"}


@dataclass
class Scene:
    id: str
    title: str
    player_text: str = ""
    keeper_text: str = ""
    clues: list[str] = field(default_factory=list)
    npcs: list[str] = field(default_factory=list)
    exits: list[Exit] = field(default_factory=list)


@dataclass
class Clue:
    id: str
    scene: str
    name: str
    player_text: str
    keeper_text: str = ""
    discover_condition: dict = field(default_factory=dict)  # {"skill": "侦查"} / {"auto": true} / {"talk": "npc_x"}
    importance: str = "main"  # main / side / red_herring
    leads_to: list[str] = field(default_factory=list)


@dataclass
class Npc:
    id: str
    name: str
    public: dict = field(default_factory=dict)   # identity / attitude / voice
    secret: dict = field(default_factory=dict)   # 永不进叙事提示词
    gives_clue: str | None = None
    stats: dict = field(default_factory=dict)


@dataclass
class Module:
    meta: dict
    background: str
    scenes: dict[str, Scene]
    clues: dict[str, Clue]
    npcs: dict[str, Npc]
    endings: list[dict]
    first_scene: str
    source_path: str = ""
    validated: bool = True

    # ---- 便捷查询 ----
    @property
    def title(self) -> str:
        return str(self.meta.get("title") or "未命名模组")

    def scene(self, scene_id: str) -> Scene:
        if scene_id not in self.scenes:
            raise ModuleError(f"场景不存在: {scene_id}")
        return self.scenes[scene_id]

    def clue(self, clue_id: str) -> Clue | None:
        return self.clues.get(clue_id)

    def npc(self, npc_id: str) -> Npc | None:
        return self.npcs.get(npc_id)

    def scene_clues(self, scene_id: str) -> list[Clue]:
        scene = self.scene(scene_id)
        return [self.clues[cid] for cid in scene.clues if cid in self.clues]

    def scene_npcs(self, scene_id: str) -> list[Npc]:
        scene = self.scene(scene_id)
        return [self.npcs[nid] for nid in scene.npcs if nid in self.npcs]


def validate_module(data: dict) -> list[str]:
    """返回问题列表；空列表代表结构可用。"""
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["模组根节点必须是对象"]

    meta = data.get("meta") or {}
    if not meta.get("title"):
        problems.append("meta.title 缺失")

    scenes_raw = data.get("scenes") or []
    if not isinstance(scenes_raw, list) or not scenes_raw:
        return problems + ["scenes 必须是非空数组"]

    scene_ids = []
    for index, raw in enumerate(scenes_raw):
        if not isinstance(raw, dict) or not raw.get("id"):
            problems.append(f"scenes[{index}] 缺少 id")
            continue
        scene_ids.append(raw["id"])
        if raw.get("clues") and not isinstance(raw["clues"], list):
            problems.append(f"场景 {raw['id']} 的 clues 必须是数组")
        if raw.get("exits") and not isinstance(raw["exits"], list):
            problems.append(f"场景 {raw['id']} 的 exits 必须是数组")

    duplicate = {sid for sid in scene_ids if scene_ids.count(sid) > 1}
    if duplicate:
        problems.append(f"场景 id 重复: {sorted(duplicate)}")

    clue_ids = []
    for raw in data.get("clues") or []:
        if not isinstance(raw, dict) or not raw.get("id"):
            problems.append("clues 中存在缺少 id 的条目")
            continue
        clue_ids.append(raw["id"])
        if raw.get("scene") not in scene_ids:
            problems.append(f"线索 {raw['id']} 指向不存在的场景 {raw.get('scene')!r}")
        if not raw.get("player_text"):
            problems.append(f"线索 {raw['id']} 缺少 player_text")

    for raw in scenes_raw:
        if not isinstance(raw, dict):
            continue
        for cid in raw.get("clues") or []:
            if cid not in clue_ids:
                problems.append(f"场景 {raw.get('id')} 引用了不存在的线索 {cid}")
        for npc_id in raw.get("npcs") or []:
            known = {n.get("id") for n in (data.get("npcs") or []) if isinstance(n, dict)}
            if npc_id not in known:
                problems.append(f"场景 {raw.get('id')} 引用了不存在的 NPC {npc_id}")
        for exit_raw in raw.get("exits") or []:
            if not isinstance(exit_raw, dict) or exit_raw.get("to") not in scene_ids:
                problems.append(f"场景 {raw.get('id')} 的出口指向不存在的场景 {exit_raw!r}")
                continue
            condition = exit_raw.get("condition") or {}
            if "clue" in condition and condition["clue"] not in clue_ids:
                problems.append(f"出口条件引用了不存在的线索 {condition['clue']}")

    for raw in data.get("endings") or []:
        if not isinstance(raw, dict) or not raw.get("id"):
            problems.append("endings 中存在缺少 id 的条目")
            continue
        condition = raw.get("condition") or {}
        if "clue" in condition and condition["clue"] not in clue_ids:
            problems.append(f"结局 {raw['id']} 的条件引用了不存在的线索 {condition['clue']}")

    first = meta.get("start_scene") or (scene_ids[0] if scene_ids else None)
    if first not in scene_ids:
        problems.append(f"起始场景 {first!r} 不存在")

    return problems


def _build_scene(raw: dict) -> Scene:
    exits = [
        Exit(to=e.get("to"), label=e.get("label") or "", condition=e.get("condition") or {})
        for e in (raw.get("exits") or [])
    ]
    return Scene(
        id=raw["id"],
        title=raw.get("title") or raw["id"],
        player_text=raw.get("player_text") or "",
        keeper_text=raw.get("keeper_text") or "",
        clues=list(raw.get("clues") or []),
        npcs=list(raw.get("npcs") or []),
        exits=exits,
    )


def module_from_dict(data: dict, *, source_path: str = "") -> Module:
    problems = validate_module(data)
    if problems:
        raise ModuleError("模组校验失败：" + "；".join(problems))

    scenes = {raw["id"]: _build_scene(raw) for raw in data["scenes"]}
    clues = {
        raw["id"]: Clue(
            id=raw["id"],
            scene=raw["scene"],
            name=raw.get("name") or raw["id"],
            player_text=raw.get("player_text") or "",
            keeper_text=raw.get("keeper_text") or "",
            discover_condition=raw.get("discover_condition") or {},
            importance=raw.get("importance") or "main",
            leads_to=list(raw.get("leads_to") or []),
        )
        for raw in (data.get("clues") or [])
    }
    npcs = {
        raw["id"]: Npc(
            id=raw["id"],
            name=raw.get("name") or raw["id"],
            public=raw.get("public") or {},
            secret=raw.get("secret") or {},
            gives_clue=raw.get("gives_clue"),
            stats=raw.get("stats") or {},
        )
        for raw in (data.get("npcs") or [])
    }
    meta = data.get("meta") or {}
    return Module(
        meta=meta,
        background=data.get("background") or "",
        scenes=scenes,
        clues=clues,
        npcs=npcs,
        endings=list(data.get("endings") or []),
        first_scene=meta.get("start_scene") or next(iter(scenes)),
        source_path=source_path,
        validated=True,
    )


def load_module(source: dict | str | Path) -> Module:
    """从字典或 JSON 文件加载模组。"""
    if isinstance(source, dict):
        return module_from_dict(source)
    path = Path(source)
    if not path.is_file():
        raise ModuleError(f"模组文件不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return module_from_dict(data, source_path=str(path))


def module_from_row(row: dict) -> Module:
    """把数据库里的一行 module 还原成 Module（P1 运行时用）。"""
    data = {
        "meta": json.loads(row["meta_json"] or "{}"),
        "background": row.get("background") or "",
        "scenes": json.loads(row.get("scenes_json") or "[]"),
        "npcs": json.loads(row.get("npcs_json") or "{}"),
        "clues": [],
        "endings": json.loads(row.get("endings_json") or "[]"),
    }
    # scenes_json 是数组；npcs_json/clues_json 是 {id: {...}} 字典
    npcs = data["npcs"]
    data["npcs"] = [dict(value, id=key) for key, value in npcs.items()] if isinstance(npcs, dict) else npcs
    clues = json.loads(row.get("clues_json") or "{}")
    data["clues"] = [dict(value, id=key) for key, value in clues.items()] if isinstance(clues, dict) else clues
    if row.get("start_scene"):
        data["meta"] = dict(data["meta"], start_scene=row["start_scene"])
    return module_from_dict(data, source_path=row.get("source_path") or "")


def dump_module(module: Module) -> dict:
    """导出回可读 JSON（便于人工校对与版本管理）。"""
    return {
        "meta": dict(module.meta),
        "background": module.background,
        "scenes": [asdict(scene) for scene in module.scenes.values()],
        "clues": [asdict(clue) for clue in module.clues.values()],
        "npcs": [asdict(npc) for npc in module.npcs.values()],
        "endings": list(module.endings),
    }
