"""帮助菜单渲染单元测试（无需启动服务，只初始化 NoneBot 后加载插件）。

运行：.venv\\Scripts\\python.exe scripts\\test_help_menu.py

验证 D-14：默认走纯文本、文本含分类与命令、超长被截断、权限过滤生效。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import nonebot  # noqa: E402

nonebot.init(driver="~fastapi", host="127.0.0.1", port=18997, superusers={"1"})
nonebot.load_plugin("src.plugins.interactive_help")

from src.plugins.interactive_help._builder import (  # noqa: E402
    MAX_TEXT_LEN,
    build_main_menu_json,
    build_main_menu_text,
    build_submenu_text,
)
from src.plugins.interactive_help._config import config_manager  # noqa: E402
from src.plugins.interactive_help._models import PermissionLevel  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK  {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


text = build_main_menu_text(PermissionLevel.USER)
print("=" * 60)
print(text)
print("=" * 60, f"({len(text)} 字)")

check("默认不使用卡片", config_manager.use_card is False)
check("含标题", config_manager.menu.title in text)
check("含漫画分类", "漫画工具" in text and "/jm" in text)
check("含影之诗分类", "影之诗查卡" in text and "/sv" in text)
check("含井字棋", "/井字棋" in text)
check("普通用户看不到管理员分类", "AI 管理" not in text, text)
check("文本长度在上限内", len(text) <= MAX_TEXT_LEN, f"{len(text)}")

admin_text = build_main_menu_text(PermissionLevel.SUPER_ADMIN)
check("超级管理员能看到 AI 管理分类", "AI 管理" in admin_text, admin_text[-200:])

sub = build_submenu_text("sv", PermissionLevel.USER)
print("-" * 60)
print(sub)
check("子菜单含分类名", "影之诗查卡" in sub)
check("子菜单含命令与发送提示", "/sv" in sub and "发送" in sub)
check("子菜单含返回提示", "/help" in sub)

missing = build_submenu_text("not_exist", PermissionLevel.USER)
check("不存在的分类给出提示", "分类不存在" in missing, missing)

card = build_main_menu_json(PermissionLevel.USER)
check("卡片模式仍可用（JSON 合法）", card.startswith("{") and "com.tencent.structmsg" in card)

print(f"\n===== {PASS} 通过 / {FAIL} 失败 =====")
sys.exit(1 if FAIL else 0)
