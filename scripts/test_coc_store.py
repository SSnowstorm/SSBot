"""P0 持久层单测：临时库，不碰 data/ 下的真实数据。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_store.py
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.plugins.coc_keeper.domain import random_investigator  # noqa: E402
from src.plugins.coc_keeper.store.db import CocStore  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK  {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="coc_store_"))
    db_path = tmp / "coc.sqlite3"
    store = CocStore(db_path)

    print("\n== 建库 ==")
    tables = {
        r[0]
        for r in store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    need = {"campaign", "module", "character", "session", "turn", "roll", "event", "clue_state", "house_rules", "meta"}
    check("P0 表齐全", need <= tables, f"missing={sorted(need - tables)}")
    check("schema 版本已写入", store.conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == "1")

    print("\n== 团与角色 ==")
    cid = store.create_campaign("测试团", group_id=123456, keeper_style="standard")
    check("建团返回 id", cid > 0)
    check("按群号可查到团", (store.find_campaign_by_group(123456) or {}).get("id") == cid)
    check("查不到的群返回 None", store.find_campaign_by_group(999) is None)

    inv = random_investigator(name="陈默")
    char_id = store.save_character(cid, inv, owner_qq=10001)
    check("存角色返回 id", char_id > 0)

    again = store.save_character(cid, inv, owner_qq=10001)
    check("同一 owner 重复保存是更新不是新增", again == char_id, f"{again} vs {char_id}")
    check("角色数量仍为 1", len(store.list_characters(cid)) == 1)

    found = store.find_character_by_owner(cid, 10001)
    check("按 owner 可查到角色", found is not None and found[0] == char_id)
    check("角色姓名一致", found[1].name == "陈默")
    check("属性完整", set(found[1].attrs) == {"STR", "CON", "SIZ", "DEX", "APP", "INT", "POW", "EDU"})
    check("按 owner 查不到时返回 None", store.find_character_by_owner(cid, 99999) is None)

    print("\n== 村规与快照 ==")
    store.set_house_rule(cid, "critical_rule", "one")
    store.set_house_rule(cid, "bonus_die_first_try", True)
    rules = store.get_house_rules(cid)
    check("村规读回", rules.get("campaign:critical_rule") == "one", json.dumps(rules, ensure_ascii=False))
    check("布尔村规保持类型", rules.get("campaign:bonus_die_first_try") is True)

    store.set_house_rule(cid, "critical_rule", "fifth")
    version = store.conn.execute(
        "SELECT version FROM house_rules WHERE campaign_id=? AND key='critical_rule'", (cid,)
    ).fetchone()[0]
    check("改村规会递增 version", version == 2, f"version={version}")

    sid = store.create_session(cid)
    session = store.get_session(sid)
    snapshot = json.loads(session["house_rules_snapshot"])
    check("开团时快照村规", snapshot.get("campaign:critical_rule") == "fifth", json.dumps(snapshot, ensure_ascii=False))
    check("会话状态 running", session["status"] == "running")
    check("可按团找 running 会话", (store.find_running_session(cid) or {}).get("id") == sid)

    print("\n== 掷骰与事件 ==")
    roll_id = store.append_roll(
        sid, actor="10001", kind="check", skill="侦查", target=65,
        difficulty="regular", d100_value=37, outcome="regular", visibility="public",
        detail={"tens": 3, "units": 7},
    )
    check("掷骰写入返回 id", roll_id > 0)
    row = store.conn.execute("SELECT * FROM roll WHERE id=?", (roll_id,)).fetchone()
    check("掷骰原始点数落库", row["d100"] == 37 and row["target"] == 65)
    check("可见性默认值", row["visibility"] == "public")

    seqs = [
        store.append_event(sid, "scene_enter", payload={"scene": "harbor"}),
        store.append_event(sid, "ooc", actor="10001", payload={"text": "ooc test"}),
        store.append_event(sid, "keeper_mercy", payload={"reason": "fail_forward"}),
    ]
    check("事件 seq 从 1 递增", seqs == [1, 2, 3], str(seqs))
    events = store.list_events(sid)
    check("事件按 seq 返回", [e["type"] for e in events] == ["scene_enter", "ooc", "keeper_mercy"])
    check("事件 payload 是 JSON 对象", isinstance(events[2]["payload"], dict) and events[2]["payload"]["reason"] == "fail_forward")
    check("事件计数", store.count_events(sid) == 3)

    print("\n== 状态更新与重连 ==")
    inv.state["hp"] = inv.hp_max - 4
    inv.state["san"] = inv.san_max - 6
    store.update_character_state(char_id, inv.state)
    store.close()

    reopened = CocStore(db_path)
    loaded = reopened.get_character(char_id)
    check("重开后角色仍在", loaded is not None)
    check("HP 状态已持久化", loaded.hp == inv.hp_max - 4, f"{loaded.hp}")
    check("SAN 状态已持久化", loaded.san == inv.san_max - 6)
    check("村规也持久化", reopened.get_house_rules(cid).get("campaign:bonus_die_first_try") is True)
    check("事件仍在", reopened.count_events(sid) == 3)
    reopened.close()

    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    print(f"（临时库：{db_path}）")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
