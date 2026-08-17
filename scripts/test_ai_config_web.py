"""ai_config_console P3 网页端到端测试。

验证：静态页挂载、登录鉴权、配置读写、人格 CRUD、用量、备份全流程。
与 test_ai_config_api.py 的区别：本测试额外验证 static/ 挂载与页面可达。
"""

import os

os.environ.setdefault("CODEBUDDY_SAFE_DELETE_SANDBOX", "0")

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock
import nonebot


class _FakeDriver:
    server_app = MagicMock()
    config = MagicMock(superusers=set())

    def on_startup(self, func):
        return func


_fake = _FakeDriver()
nonebot.get_driver = lambda: _fake

# stub suggarchat 子模块（避免 require 链，__init__ 导入 _inject_guard 会触发）
import types

for _name, _attrs in {
    "nonebot_plugin_suggarchat": {},
    "nonebot_plugin_suggarchat.on_event": {
        "on_before_chat": lambda *a, **k: type("M", (), {
            "append_handler": lambda self, f: f, "priority": 1, "block": False
        })()
    },
    "nonebot_plugin_suggarchat.event": {"BeforeChatEvent": object},
    "nonebot_plugin_suggarchat.matcher": {"Matcher": object},
}.items():
    _m = types.ModuleType(_name)
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)
    sys.modules[_name] = _m

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from src.plugins.ai_config_console import _config_store
from src.plugins.ai_config_console._api import router
from src.plugins.ai_config_console._auth import generate_token, set_token

STATIC_DIR = Path(__file__).resolve().parents[1] / "src" / "plugins" / "ai_config_console" / "static"

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
    config_bak = _config_store.CONFIG_PATH.with_suffix(".toml.bak")
    shutil.copy2(_config_store.CONFIG_PATH, config_bak)
    print(f"== 已备份真实 config 到 {config_bak.name} ==")

    try:
        app = FastAPI()
        app.include_router(router, prefix="/ai-config/api")
        app.mount("/ai-config", StaticFiles(directory=STATIC_DIR, html=True))
        token = generate_token()
        set_token(token)
        client = TestClient(app)
        h = {"X-AI-Config-Token": token}

        # 1. 静态页可达
        print("\n== 1. 静态页 ==")
        r = client.get("/ai-config/")
        check("index.html 200", r.status_code == 200, f"got {r.status_code}")
        check("包含配置台标题", "AI 配置台" in r.text)
        check("包含 API 前缀", "/ai-config/api" in r.text)
        r = client.get("/ai-config/index.html")
        check("index.html 显式路径 200", r.status_code == 200)

        # 2. 登录鉴权
        print("\n== 2. 鉴权 ==")
        r = client.get("/ai-config/api/status")
        check("无 token 401", r.status_code == 401)
        r = client.get("/ai-config/api/status", headers=h)
        check("有 token 200", r.status_code == 200)

        # 3. 配置读写（含 admin 组）
        print("\n== 3. 配置 ==")
        r = client.get("/ai-config/api/config", headers=h)
        check("GET config 200", r.status_code == 200)
        data = r.json()
        check("9 组", len(data) == 9, f"got {len(data)}")
        check("admin.admins 可写", data["admin"]["admins"]["editable"] is True)
        check("api_key 打码", "****" in str(data["model"]["api_key"]["value"]))
        # 写一个值再恢复
        old = data["session"]["session_max_tokens"]["value"]
        r = client.put("/ai-config/api/config", headers=h, json={"session": {"session_max_tokens": old + 1}})
        check("PUT config 200", r.status_code == 200)
        r = client.get("/ai-config/api/config", headers=h)
        check("写入生效", r.json()["session"]["session_max_tokens"]["value"] == old + 1)

        # 4. 人格 CRUD
        print("\n== 4. 人格 ==")
        r = client.put("/ai-config/api/prompts/group/test_web", headers=h, json={"content": "网页测试人格"})
        check("创建 200", r.status_code == 200)
        r = client.get("/ai-config/api/prompts/group/test_web", headers=h)
        check("读取一致", r.status_code == 200 and r.json()["content"] == "网页测试人格")
        r = client.delete("/ai-config/api/prompts/group/test_web", headers=h)
        check("删除 200", r.status_code == 200)

        # 5. 用量
        print("\n== 5. 用量 ==")
        r = client.get("/ai-config/api/usage?days=7", headers=h)
        check("usage 200", r.status_code == 200 and len(r.json()["daily"]) == 7)

        # 6. 备份
        print("\n== 6. 备份 ==")
        r = client.post("/ai-config/api/backup", headers=h)
        check("backup 200", r.status_code == 200 and Path(r.json()["backup_path"]).exists())

    finally:
        shutil.copy2(config_bak, _config_store.CONFIG_PATH)
        config_bak.unlink(missing_ok=True)
        print("\n== 已恢复真实 config.toml ==")

    print(f"\n===== 结果: {PASS} 通过, {FAIL} 失败 =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
