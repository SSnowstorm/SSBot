-- CoC Keeper P0 数据库结构（SQLite）
-- 约定：所有 *_json 字段存 UTF-8 JSON 字符串（ensure_ascii=False）

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- 团（一次长战役；一个群可以先后开多个团）
CREATE TABLE IF NOT EXISTS campaign (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id     INTEGER,
    module_id    INTEGER,
    title        TEXT,
    status       TEXT DEFAULT 'idle',      -- idle / running / paused / ended
    keeper_style TEXT DEFAULT 'standard',  -- lenient / standard / cruel
    created_at   TEXT,
    updated_at   TEXT
);

-- 模组（结构化后的剧本，P2 才真正写入）
CREATE TABLE IF NOT EXISTS module (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT,
    version        TEXT,
    author         TEXT,
    meta_json      TEXT,
    background     TEXT,
    source_path    TEXT,
    scenes_json    TEXT,
    npcs_json      TEXT,
    clues_json     TEXT,
    timeline_json  TEXT,
    endings_json   TEXT,
    handouts_json  TEXT,
    validated      INTEGER DEFAULT 0,
    created_at     TEXT
);

-- 角色卡（PC 与 NPC 共用）
CREATE TABLE IF NOT EXISTS character (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id    INTEGER REFERENCES campaign(id) ON DELETE CASCADE,
    module_id      INTEGER,
    type           TEXT NOT NULL CHECK (type IN ('pc', 'npc')),
    name           TEXT NOT NULL,
    owner_qq       INTEGER,
    occupation     TEXT,
    attrs_json     TEXT NOT NULL,
    skills_json    TEXT,
    derived_json   TEXT,                    -- 当前 HP/MP/SAN/幸运
    condition_json TEXT,                    -- 重伤/濒死/疯狂等状态
    items_json     TEXT,
    public_json    TEXT,
    secret_json    TEXT,
    created_at     TEXT,
    updated_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_character_campaign ON character(campaign_id, type);
CREATE INDEX IF NOT EXISTS idx_character_owner ON character(campaign_id, owner_qq);

-- 会话（一局）
CREATE TABLE IF NOT EXISTS session (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id          INTEGER REFERENCES campaign(id) ON DELETE CASCADE,
    status               TEXT DEFAULT 'idle',
    current_scene        TEXT,
    turn_no              INTEGER DEFAULT 0,
    house_rules_snapshot TEXT,             -- 开局村规快照（Q1）
    started_at           TEXT,
    ended_at             TEXT
);

-- 回合
CREATE TABLE IF NOT EXISTS turn (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     INTEGER REFERENCES session(id) ON DELETE CASCADE,
    no             INTEGER,
    scene_id       TEXT,
    declared_json  TEXT,
    resolution_json TEXT,
    narrative      TEXT,
    created_at     TEXT
);

-- 掷骰（复盘的事实源：记录原始点数，不记录"成功/失败"结论）
CREATE TABLE IF NOT EXISTS roll (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER REFERENCES session(id) ON DELETE CASCADE,
    turn_id       INTEGER,
    actor         TEXT,
    kind          TEXT,                    -- check / san / damage / luck / opposed
    skill         TEXT,
    target        INTEGER,
    difficulty    TEXT,
    bonus_penalty INTEGER DEFAULT 0,
    d100          INTEGER,
    outcome       TEXT,
    visibility    TEXT DEFAULT 'public',   -- public / private / kp_only（Q5）
    detail_json   TEXT,
    created_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_roll_session ON roll(session_id, id);

-- 事件（append-only）
CREATE TABLE IF NOT EXISTS event (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER REFERENCES session(id) ON DELETE CASCADE,
    seq          INTEGER,
    type         TEXT NOT NULL,
    actor        TEXT,
    payload_json TEXT,
    created_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_event_session ON event(session_id, seq);

-- 线索发现状态（P1 使用，先建表）
CREATE TABLE IF NOT EXISTS clue_state (
    session_id    INTEGER REFERENCES session(id) ON DELETE CASCADE,
    clue_id       TEXT NOT NULL,
    discovered_by TEXT,
    discovered_at TEXT,
    scene_id      TEXT,
    PRIMARY KEY (session_id, clue_id)
);

-- 村规（Q1：结构化持久化；开团时快照进 session）
CREATE TABLE IF NOT EXISTS house_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER REFERENCES campaign(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    value_json  TEXT NOT NULL,
    scope       TEXT DEFAULT 'campaign',   -- campaign / scene
    version     INTEGER DEFAULT 1,
    updated_at  TEXT,
    UNIQUE (campaign_id, key, scope)
);
