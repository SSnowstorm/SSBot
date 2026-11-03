"""P0 命令层接线测试：初始化 NoneBot、加载插件、走一遍「建团 → 存卡 → 检定」。

不启动 HTTP 服务、不发 QQ 消息；只验证命令层依赖的辅助函数与数据库接线。

运行：.venv\\Scripts\\python.exe scripts\\test_coc_commands.py
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="coc_cmd_"))
os.environ["COC_DB_PATH"] = str(TMP / "coc.sqlite3")

import nonebot  # noqa: E402

nonebot.init(driver="~fastapi", host="127.0.0.1", port=18996, superusers={"1"})
nonebot.load_plugin("src.plugins.coc_keeper")

from src.plugins.coc_keeper import _commands  # noqa: E402
from src.plugins.coc_keeper.domain import Difficulty, resolve  # noqa: E402

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


class FakeEvent:
    """只提供命令层用到的字段。"""

    def __init__(self, user_id: int, group_id: int | None = None, nickname: str = "测试员"):
        self.user_id = user_id
        self.group_id = group_id
        self.sender = type("S", (), {"nickname": nickname})()


def main() -> None:
    print("== 作用域解析 ==")
    group_event = FakeEvent(10001, 527020285)
    private_event = FakeEvent(10001, None)
    check("群聊作用域 = 群号", _commands._here(group_event) == 527020285)
    check("私聊作用域 = 负用户号", _commands._here(private_event) == -10001)

    print("\n== 团与角色 ==")
    cid = _commands._ensure_campaign(group_event)
    check("首次调用自动建团", cid > 0)
    check("再次调用复用同一个团", _commands._ensure_campaign(group_event) == cid)

    store = _commands.get_store()
    check("store 指向临时库", str(store.path).endswith("coc.sqlite3"), str(store.path))
    check("store 是单例", _commands.get_store() is store)

    from src.plugins.coc_keeper.domain import random_investigator

    inv = random_investigator(name="接线测试员")
    char_id = store.save_character(cid, inv, owner_qq=10001)
    found = store.find_character_by_owner(cid, 10001)
    check("角色可按 owner 取回", found is not None and found[0] == char_id)

    sheet = _commands.format_sheet(found[1])
    check("角色卡渲染含 HP/SAN", "HP" in sheet and "SAN" in sheet, sheet[:80])
    check("角色卡渲染含技能行", "侦查" in sheet, sheet[-80:])

    print("\n== 检定链路 ==")
    _, loaded = found
    skill_value = loaded.skill_value("侦查")
    result = resolve("侦查", skill_value, Difficulty.REGULAR)
    check("检定目标值 = 技能值", result.target == skill_value, f"{result.target} vs {skill_value}")
    check("检定结果在 1-100", 1 <= result.roll <= 100)
    check("摘要含技能名与目标值", "侦查" in result.summary() and str(result.target) in result.summary(),
          result.summary())

    session_id = store.create_session(cid)
    store.append_roll(
        session_id, actor="10001", kind="check", skill="侦查",
        target=result.target, difficulty=result.difficulty.value,
        d100_value=result.roll, outcome=result.outcome.value, detail=result.detail,
    )
    row = store.conn.execute("SELECT skill, d100, target FROM roll ORDER BY id DESC LIMIT 1").fetchone()
    check("掷骰记录写入会话", row is not None and row["skill"] == "侦查", str(dict(row) if row else None))

    print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
    print(f"（临时库：{store.path}）")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
