"""SQLite 持久层：建表、CRUD、事件与掷骰记录。

设计要点：
- 独立数据库文件（默认 ``data/coc_keeper/coc.sqlite3``），不复用 suggarchat 的 ORM 库
- 事件表 append-only，``seq`` 按会话自增，作为复盘的时间线
- 掷骰记录保存原始点数与目标值，保证复盘可核对
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from ..domain.character import Investigator

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = "1"

DEFAULT_DB_PATH = Path(__file__).resolve().parents[4] / "data" / "coc_keeper" / "coc.sqlite3"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(text, default=None):
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


class CocStore:
    """coc_keeper 的唯一数据库入口。"""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    # ---------- 基础设施 ----------

    def _ensure_schema(self) -> None:
        self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self._migrate()
        row = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?)", (SCHEMA_VERSION,)
            )
        self.conn.commit()

    def _migrate(self) -> None:
        """轻量迁移：只做「缺列就加列」，够 P1 用，正式迁移等 P2。"""
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(session)")}
        if "state_json" not in columns:
            self.conn.execute("ALTER TABLE session ADD COLUMN state_json TEXT")
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(module)")}
        if "start_scene" not in columns:
            self.conn.execute("ALTER TABLE module ADD COLUMN start_scene TEXT")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "CocStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------- 团 ----------

    def create_campaign(
        self,
        title: str,
        *,
        group_id: int | None = None,
        module_id: int | None = None,
        keeper_style: str = "standard",
    ) -> int:
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO campaign(group_id, module_id, title, status, keeper_style, created_at, updated_at)"
            " VALUES(?,?,?,'idle',?,?,?)",
            (group_id, module_id, title, keeper_style, now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_campaign(self, campaign_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM campaign WHERE id=?", (campaign_id,)).fetchone()
        return dict(row) if row else None

    def set_campaign_module(self, campaign_id: int, module_id: int) -> None:
        self.conn.execute(
            "UPDATE campaign SET module_id=?, updated_at=? WHERE id=?",
            (module_id, _now(), campaign_id),
        )
        self.conn.commit()

    def find_campaign_by_group(self, group_id: int) -> dict | None:
        """按群号找最近的团（一群同时只跑一个 running 团，Q2）。"""
        row = self.conn.execute(
            "SELECT * FROM campaign WHERE group_id=? ORDER BY"
            " CASE status WHEN 'running' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END, id DESC LIMIT 1",
            (group_id,),
        ).fetchone()
        return dict(row) if row else None

    def latest_session(self, campaign_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM session WHERE campaign_id=? ORDER BY id DESC LIMIT 1", (campaign_id,)
        ).fetchone()
        return dict(row) if row else None

    def find_running_session(self, campaign_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM session WHERE campaign_id=? AND status='running' ORDER BY id DESC LIMIT 1",
            (campaign_id,),
        ).fetchone()
        return dict(row) if row else None

    # ---------- 角色 ----------

    def save_character(
        self,
        campaign_id: int,
        inv: Investigator,
        *,
        type_: str = "pc",
        owner_qq: int | None = None,
        module_id: int | None = None,
    ) -> int:
        """新建或更新角色（按 campaign + name + owner 判定是否已存在）。"""
        now = _now()
        payload = (
            campaign_id, module_id, type_, inv.name, owner_qq, inv.occupation,
            _dumps(inv.attrs), _dumps(inv.skills), _dumps(inv.state),
            _dumps([]), _dumps({}), _dumps(inv.public), _dumps(inv.secret),
            now, now,
        )
        existing = None
        if owner_qq is not None:
            existing = self.conn.execute(
                "SELECT id FROM character WHERE campaign_id=? AND owner_qq=? AND type='pc'",
                (campaign_id, owner_qq),
            ).fetchone()
        if existing is None:
            existing = self.conn.execute(
                "SELECT id FROM character WHERE campaign_id=? AND name=? AND type=?",
                (campaign_id, inv.name, type_),
            ).fetchone()

        if existing is None:
            cur = self.conn.execute(
                "INSERT INTO character(campaign_id, module_id, type, name, owner_qq, occupation,"
                " attrs_json, skills_json, derived_json, condition_json, items_json,"
                " public_json, secret_json, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                payload,
            )
            self.conn.commit()
            return int(cur.lastrowid)

        char_id = int(existing["id"])
        self.conn.execute(
            "UPDATE character SET module_id=?, type=?, name=?, owner_qq=?, occupation=?,"
            " attrs_json=?, skills_json=?, derived_json=?, condition_json=?, items_json=?,"
            " public_json=?, secret_json=?, updated_at=? WHERE id=?",
            (
                module_id, type_, inv.name, owner_qq, inv.occupation,
                _dumps(inv.attrs), _dumps(inv.skills), _dumps(inv.state),
                _dumps([]), _dumps({}), _dumps(inv.public), _dumps(inv.secret), now, char_id,
            ),
        )
        self.conn.commit()
        return char_id

    @staticmethod
    def _row_to_investigator(row: sqlite3.Row) -> Investigator:
        return Investigator(
            name=row["name"],
            occupation=row["occupation"] or "调查员",
            attrs=_loads(row["attrs_json"], {}) or {},
            skills=_loads(row["skills_json"], {}) or {},
            public=_loads(row["public_json"], {}) or {},
            secret=_loads(row["secret_json"], {}) or {},
            state=_loads(row["derived_json"], {}) or {},
        )

    def get_character(self, character_id: int) -> Investigator | None:
        row = self.conn.execute("SELECT * FROM character WHERE id=?", (character_id,)).fetchone()
        return self._row_to_investigator(row) if row else None

    def find_character_by_owner(self, campaign_id: int, owner_qq: int) -> tuple[int, Investigator] | None:
        row = self.conn.execute(
            "SELECT * FROM character WHERE campaign_id=? AND owner_qq=? AND type='pc'"
            " ORDER BY id DESC LIMIT 1",
            (campaign_id, owner_qq),
        ).fetchone()
        if row is None:
            return None
        return int(row["id"]), self._row_to_investigator(row)

    def list_characters(self, campaign_id: int, type_: str | None = None) -> list[dict]:
        sql = "SELECT id, type, name, owner_qq, occupation, derived_json, updated_at FROM character WHERE campaign_id=?"
        params: list = [campaign_id]
        if type_:
            sql += " AND type=?"
            params.append(type_)
        sql += " ORDER BY id"
        result = []
        for row in self.conn.execute(sql, params):
            state = _loads(row["derived_json"], {}) or {}
            result.append({
                "id": int(row["id"]),
                "type": row["type"],
                "name": row["name"],
                "owner_qq": row["owner_qq"],
                "occupation": row["occupation"],
                "hp": state.get("hp"),
                "san": state.get("san"),
                "updated_at": row["updated_at"],
            })
        return result

    def update_character_state(self, character_id: int, state: dict) -> None:
        self.conn.execute(
            "UPDATE character SET derived_json=?, updated_at=? WHERE id=?",
            (_dumps(state), _now(), character_id),
        )
        self.conn.commit()

    # ---------- 村规 ----------

    def set_house_rule(self, campaign_id: int, key: str, value, scope: str = "campaign") -> None:
        self.conn.execute(
            "INSERT INTO house_rules(campaign_id, key, value_json, scope, version, updated_at)"
            " VALUES(?,?,?,?,1,?)"
            " ON CONFLICT(campaign_id, key, scope) DO UPDATE SET"
            " value_json=excluded.value_json, version=house_rules.version+1, updated_at=excluded.updated_at",
            (campaign_id, key, _dumps(value), scope, _now()),
        )
        self.conn.commit()

    def get_house_rules(self, campaign_id: int) -> dict:
        rules: dict = {}
        for row in self.conn.execute(
            "SELECT key, value_json, scope FROM house_rules WHERE campaign_id=? ORDER BY key",
            (campaign_id,),
        ):
            rules[f"{row['scope']}:{row['key']}"] = _loads(row["value_json"])
        return rules

    # ---------- 会话 / 回合 ----------

    def create_session(self, campaign_id: int) -> int:
        snapshot = _dumps(self.get_house_rules(campaign_id))
        cur = self.conn.execute(
            "INSERT INTO session(campaign_id, status, current_scene, turn_no, house_rules_snapshot, started_at)"
            " VALUES(?, 'running', NULL, 0, ?, ?)",
            (campaign_id, snapshot, _now()),
        )
        self.conn.execute("UPDATE campaign SET status='running', updated_at=? WHERE id=?", (_now(), campaign_id))
        self.conn.commit()
        return int(cur.lastrowid)

    def get_session(self, session_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM session WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def update_session(self, session_id: int, *, scene: str | None = None, turn_no: int | None = None) -> None:
        if scene is not None:
            self.conn.execute("UPDATE session SET current_scene=? WHERE id=?", (scene, session_id))
        if turn_no is not None:
            self.conn.execute("UPDATE session SET turn_no=? WHERE id=?", (turn_no, session_id))
        self.conn.commit()

    def end_session(self, session_id: int) -> None:
        now = _now()
        row = self.conn.execute("SELECT campaign_id FROM session WHERE id=?", (session_id,)).fetchone()
        self.conn.execute(
            "UPDATE session SET status='ended', ended_at=? WHERE id=?", (now, session_id)
        )
        if row is not None:
            self.conn.execute(
                "UPDATE campaign SET status='ended', updated_at=? WHERE id=?",
                (now, int(row["campaign_id"])),
            )
        self.conn.commit()

    def create_turn(self, session_id: int, no: int, scene_id: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO turn(session_id, no, scene_id, created_at) VALUES(?,?,?,?)",
            (session_id, no, scene_id, _now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    # ---------- 运行时状态 ----------

    def update_session_state(self, session_id: int, state: dict) -> None:
        self.conn.execute(
            "UPDATE session SET state_json=? WHERE id=?", (_dumps(state), session_id)
        )
        self.conn.commit()

    def get_session_state(self, session_id: int) -> dict:
        row = self.conn.execute("SELECT state_json FROM session WHERE id=?", (session_id,)).fetchone()
        return (_loads(row["state_json"], {}) or {}) if row else {}

    # ---------- 模组 ----------

    def save_module(self, module) -> int:
        """写入（或按标题+版本覆盖）一个模组，返回 module_id。"""
        meta = module.meta or {}
        row = self.conn.execute(
            "SELECT id FROM module WHERE title=? AND version=?",
            (meta.get("title"), meta.get("version")),
        ).fetchone()
        payload = (
            meta.get("title"), meta.get("version"), meta.get("author"),
            _dumps(meta), module.background, module.source_path,
            _dumps([asdict(s) for s in module.scenes.values()]),
            _dumps({k: asdict(v) for k, v in module.npcs.items()}),
            _dumps({k: asdict(v) for k, v in module.clues.items()}),
            _dumps([]), _dumps(module.endings), _dumps([]),
            1 if module.validated else 0, _now(), module.first_scene,
        )
        if row is None:
            cur = self.conn.execute(
                "INSERT INTO module(title, version, author, meta_json, background, source_path,"
                " scenes_json, npcs_json, clues_json, timeline_json, endings_json, handouts_json,"
                " validated, created_at, start_scene)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                payload,
            )
            self.conn.commit()
            return int(cur.lastrowid)
        module_id = int(row["id"])
        self.conn.execute(
            "UPDATE module SET author=?, meta_json=?, background=?, source_path=?, scenes_json=?,"
            " npcs_json=?, clues_json=?, endings_json=?, validated=?, start_scene=? WHERE id=?",
            (
                meta.get("author"), _dumps(meta), module.background, module.source_path,
                _dumps([asdict(s) for s in module.scenes.values()]),
                _dumps({k: asdict(v) for k, v in module.npcs.items()}),
                _dumps({k: asdict(v) for k, v in module.clues.items()}),
                _dumps(module.endings), 1 if module.validated else 0,
                module.first_scene, module_id,
            ),
        )
        self.conn.commit()
        return module_id

    def get_module(self, module_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM module WHERE id=?", (module_id,)).fetchone()
        return dict(row) if row else None

    def find_module_by_title(self, title: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM module WHERE title=? ORDER BY id DESC LIMIT 1", (title,)
        ).fetchone()
        return dict(row) if row else None

    # ---------- 线索 ----------

    def discover_clue(self, session_id: int, clue_id: str, *, by: str = "", scene_id: str = "") -> bool:
        """记录线索发现；已发现过返回 False。"""
        try:
            self.conn.execute(
                "INSERT INTO clue_state(session_id, clue_id, discovered_by, discovered_at, scene_id)"
                " VALUES(?,?,?,?,?)",
                (session_id, clue_id, by, _now(), scene_id),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def discovered_clues(self, session_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT clue_id, discovered_by, discovered_at, scene_id FROM clue_state"
            " WHERE session_id=? ORDER BY discovered_at",
            (session_id,),
        )
        return [dict(r) for r in rows]

    def has_clue(self, session_id: int, clue_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM clue_state WHERE session_id=? AND clue_id=?", (session_id, clue_id)
        ).fetchone()
        return row is not None

    # ---------- 掷骰 / 事件 ----------

    def append_roll(
        self,
        session_id: int,
        *,
        actor: str,
        kind: str,
        skill: str = "",
        target: int | None = None,
        difficulty: str = "",
        bonus_penalty: int = 0,
        d100_value: int | None = None,
        outcome: str = "",
        visibility: str = "public",
        detail: dict | None = None,
        turn_id: int | None = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO roll(session_id, turn_id, actor, kind, skill, target, difficulty,"
            " bonus_penalty, d100, outcome, visibility, detail_json, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                session_id, turn_id, str(actor), kind, skill, target, difficulty,
                int(bonus_penalty), d100_value, outcome, visibility,
                _dumps(detail or {}), _now(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_rolls(self, session_id: int, limit: int = 500) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM roll WHERE session_id=? ORDER BY id LIMIT ?", (session_id, int(limit))
        )
        return [dict(r) for r in rows]

    def append_event(self, session_id: int, type_: str, *, actor: str | None = None, payload: dict | None = None) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(seq), 0) AS last FROM event WHERE session_id=?", (session_id,)
        ).fetchone()
        seq = int(row["last"]) + 1
        cur = self.conn.execute(
            "INSERT INTO event(session_id, seq, type, actor, payload_json, created_at)"
            " VALUES(?,?,?,?,?,?)",
            (session_id, seq, type_, actor, _dumps(payload or {}), _now()),
        )
        self.conn.commit()
        return seq

    def list_events(self, session_id: int, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT seq, type, actor, payload_json, created_at FROM event"
            " WHERE session_id=? ORDER BY seq LIMIT ?",
            (session_id, int(limit)),
        )
        return [
            {
                "seq": int(r["seq"]),
                "type": r["type"],
                "actor": r["actor"],
                "payload": _loads(r["payload_json"], {}),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def count_events(self, session_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM event WHERE session_id=?", (session_id,)
        ).fetchone()
        return int(row["n"])
