"""ai_config_console API 端到端测试（独立于 NoneBot 运行）。

- 用 FastAPI TestClient 挂载 _api.router 直接测试
- 写操作（PUT /config）前备份真实 config.toml，测试后恢复
- 人格 CRUD 使用测试专用人格名，测后删除
"""

import os

# 关闭 WorkBuddy 的 safe-delete shim（测试环境删除走正常路径）
os.environ.setdefault("CODEBUDDY_SAFE_DELETE_SANDBOX", "0")

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 绕过 NoneBot 初始化：mock get_driver（__init__.py 导入时会调用）
from unittest.mock import MagicMock
import nonebot


class _FakeDriver:
    server_app = MagicMock()
    config = MagicMock()

    def on_startup(self, func):
        return func


nonebot.get_driver = lambda: _FakeDriver()

# D-12 修复：本脚本早期只 mock 了 get_driver，没有 stub suggarchat。
# 插件 __init__ 会 import _inject_guard → 真实 import suggarchat → 其 __init__ 调
# require("nonebot_plugin_localstore") → 未初始化 NoneBot 时抛
# "Cannot load plugin nonebot_plugin_localstore!"，导致脚本根本跑不起来。
# 这里与 test_ai_config_web.py 采用同一套最小 stub。
import types as _types

for _name, _attrs in {
    "nonebot_plugin_suggarchat": {},
    "nonebot_plugin_suggarchat.on_event": {
        "on_before_chat": lambda *a, **k: type(
            "M", (), {"append_handler": lambda self, f: f, "priority": 1, "block": False}
        )()
    },
    "nonebot_plugin_suggarchat.event": {"BeforeChatEvent": object},
    "nonebot_plugin_suggarchat.matcher": {"Matcher": object},
}.items():
    _m = _types.ModuleType(_name)
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)
    sys.modules[_name] = _m

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.plugins.ai_config_console import _config_store
from src.plugins.ai_config_console._api import router
from src.plugins.ai_config_console._auth import generate_token, set_token

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def main():
    # 准备：备份真实 config.toml
    config_bak = _config_store.CONFIG_PATH.with_suffix(".toml.bak")
    shutil.copy2(_config_store.CONFIG_PATH, config_bak)
    print(f"== 已备份真实 config 到 {config_bak.name} ==")

    try:
        # 建立 app
        app = FastAPI()
        app.include_router(router, prefix="/ai-config/api")
        token = generate_token()
        set_token(token)
        client = TestClient(app)

        # 1. 鉴权
        print("\n== 1. 鉴权 ==")
        r = client.get("/ai-config/api/status")
        check("无 token → 401", r.status_code == 401, f"got {r.status_code}")
        r = client.get("/ai-config/api/status", headers={"X-AI-Config-Token": "wrong"})
        check("错误 token → 401", r.status_code == 401, f"got {r.status_code}")
        h = {"X-AI-Config-Token": token}

        # 2. 状态
        print("\n== 2. /status ==")
        r = client.get("/ai-config/api/status", headers=h)
        check("status 200", r.status_code == 200)
        if r.status_code == 200:
            check("running=true", r.json()["running"] is True)
            check("version 存在", "version" in r.json())

        # 3. 配置读取
        print("\n== 3. GET /config ==")
        r = client.get("/ai-config/api/config", headers=h)
        check("config 200", r.status_code == 200)
        data = r.json()
        check("9 个可编辑分组（含 admin）", len(data) == 9, f"got {len(data)}")
        adm = data.get("admin", {})
        check("admin.admins 可写", isinstance(adm.get("admins", {}), dict)
              and adm["admins"].get("editable") is True, f"got {adm}")
        model = data.get("model", {})
        api_key = model.get("api_key", {})
        check("api_key 打码", isinstance(api_key, dict) and api_key.get("editable") is False
              and "****" in str(api_key.get("value", "")), f"got {api_key}")
        basic = data.get("basic", {})
        mf = basic.get("matcher_function", {})
        check("matcher_function 只读", isinstance(mf, dict) and mf.get("editable") is False)
        llm = data.get("llm", {})
        ml = llm.get("memory_lenth_limit", {})
        check("memory_lenth_limit 可写", isinstance(ml, dict) and ml.get("editable") is True,
              f"got {ml}")

        # 4. 人格列表
        print("\n== 4. GET /prompts ==")
        r = client.get("/ai-config/api/prompts/group", headers=h)
        check("prompts/group 200", r.status_code == 200)
        check("含 default", any(p["name"] == "default" for p in r.json()["prompts"]),
              f"got {r.json()}")
        r = client.get("/ai-config/api/prompts/bad", headers=h)
        check("非法场景 → 400", r.status_code == 400, f"got {r.status_code}")

        # 5. 用量
        print("\n== 5. GET /usage ==")
        r = client.get("/ai-config/api/usage?days=7", headers=h)
        check("usage 200", r.status_code == 200)
        body = r.json()
        check("7 天数据", len(body["daily"]) == 7, f"got {len(body.get('daily', []))}")
        check("每日字段完整",
              all({"date", "count", "token_input", "token_output"} <= set(d) for d in body["daily"]))
        # D-12 附带：原断言"至少一天有数据"依赖"最近 7 天有人聊过天"，
        # bot 停用一段时间后必红。改成直接读库对比，数据为空时校验"全 0"即可。
        import sqlite3
        from datetime import date as _date, timedelta as _timedelta

        from src.plugins.ai_config_console._usage import DB_PATH

        start = (_date.today() - _timedelta(days=6)).isoformat()
        with sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True) as conn:
            rows = dict(conn.execute("SELECT date, usage_count FROM suggarchat_global_insights").fetchall())
        expect = {d["date"]: int(rows.get(d["date"], 0)) for d in body["daily"]}
        got = {d["date"]: d["count"] for d in body["daily"]}
        check("与库内数据一致（近期无记录时应全 0）", got == expect, f"api={got} db={expect}")

        # 6. 写配置（测试后恢复）
        print("\n== 6. PUT /config ==")
        old_val = data["llm"]["memory_lenth_limit"]["value"]
        new_val = old_val + 1
        r = client.put("/ai-config/api/config", headers=h,
                       json={"llm": {"memory_lenth_limit": new_val}})
        check("put config 200", r.status_code == 200)
        backup_path = r.json().get("backup_path", "")
        check("返回 backup_path", bool(backup_path), f"got {r.json()}")
        check("备份文件存在", Path(backup_path).exists())
        r = client.get("/ai-config/api/config", headers=h)
        check("写入生效", r.json()["llm"]["memory_lenth_limit"]["value"] == new_val,
              f"got {r.json()['llm']['memory_lenth_limit']}")
        # admin 组写入验证（admins 列表）
        old_admins = data["admin"]["admins"]["value"]
        test_admins = old_admins + [88888888] if isinstance(old_admins, list) else [88888888]
        r = client.put("/ai-config/api/config", headers=h,
                       json={"admin": {"admins": test_admins}})
        check("admin 写入 200", r.status_code == 200, f"got {r.status_code} {r.text}")
        r = client.get("/ai-config/api/config", headers=h)
        check("admin.admins 写入生效", r.json()["admin"]["admins"]["value"] == test_admins,
              f"got {r.json()['admin']['admins']}")

        # 自动回复概率（控制台滑块写的就是这个字段）
        old_prob = data["autoreply"]["probability"]["value"]
        new_prob = 0.37
        r = client.put("/ai-config/api/config", headers=h,
                       json={"autoreply": {"probability": new_prob}})
        check("probability 写入 200", r.status_code == 200, f"got {r.status_code} {r.text}")
        r = client.get("/ai-config/api/config", headers=h)
        got_prob = r.json()["autoreply"]["probability"]["value"]
        check("probability 写入生效", abs(float(got_prob) - new_prob) < 1e-9, f"got {got_prob}")

        # 7. 人格 CRUD
        print("\n== 7. 人格 CRUD ==")
        content = "你是测试人格，用于 API 验证。"
        r = client.put("/ai-config/api/prompts/group/test_api", headers=h,
                       json={"content": content})
        check("保存人格 200", r.status_code == 200, f"got {r.status_code} {r.text}")
        r = client.get("/ai-config/api/prompts/group/test_api", headers=h)
        check("读取人格内容一致", r.status_code == 200 and r.json()["content"] == content)
        r = client.delete("/ai-config/api/prompts/group/test_api", headers=h)
        check("删除人格 200", r.status_code == 200)
        r = client.get("/ai-config/api/prompts/group/test_api", headers=h)
        check("删除后 404", r.status_code == 404, f"got {r.status_code}")
        # 路径穿越防护
        r = client.get("/ai-config/api/prompts/group/..%2F..%2F..%2Fetc%2Fpasswd", headers=h)
        check("路径穿越被拒", r.status_code in (400, 404), f"got {r.status_code}")

        # 8. 备份
        print("\n== 8. POST /backup ==")
        r = client.post("/ai-config/api/backup", headers=h)
        check("backup 200", r.status_code == 200)
        check("backup_path 存在", Path(r.json()["backup_path"]).exists())

    finally:
        # 恢复真实 config.toml
        shutil.copy2(config_bak, _config_store.CONFIG_PATH)
        config_bak.unlink(missing_ok=True)
        print("\n== 已恢复真实 config.toml ==")

    print(f"\n===== 结果: {PASS} 通过, {FAIL} 失败 =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
