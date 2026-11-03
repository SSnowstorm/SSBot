"""插件加载冒烟测试。

验证"改完的插件能不能被 NoneBot 正常加载"：matcher 注册、装饰器参数、
import 链是否还有残留错误。

注意：加载顺序必须与 bot.py 一致——`ai_config_console` 的注入钩子依赖
suggarchat 已加载（先加载 suggarchat，再加载配置台）。

特点：不启动 HTTP 服务、不连 QQ、不写真实配置；数据库指向临时文件。
（suggarchat 在 import 期会读 AppData 下的 config.toml，只读不改。）

运行：
    .venv\\Scripts\\python.exe scripts\\smoke_plugins.py
退出码：0 = 期望插件全部加载成功，1 = 有缺失。
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# nonebot.load_plugins 的参数是"待扫描的目录"（相对 cwd），必须在项目根目录下执行
os.chdir(Path(__file__).resolve().parents[1])

TMP = Path(tempfile.mkdtemp(prefix="ssbot_smoke_"))
os.environ["SQLALCHEMY_DATABASE_URL"] = f"sqlite+aiosqlite:///{(TMP / 'db.sqlite3').as_posix()}"

import nonebot  # noqa: E402
from nonebot.adapters.onebot.v11 import Adapter  # noqa: E402

nonebot.init(
    driver="~fastapi",
    host="127.0.0.1",
    port=18999,
    superusers={"10001"},
    command_start={"/"},
)

nonebot.get_driver().register_adapter(Adapter)

# 与 bot.py 完全相同的加载顺序
TARGETS = [
    ("load_plugins", "src/plugins/plugin_nonebot_rand_qinghua"),
    ("load_plugins", "src/plugins/jm_downloader"),
    ("load_plugins", "src/plugins/get_group_info"),
    ("load_plugin", "src.plugins.interactive_help"),
    ("load_plugin", "src.plugins.sv_card"),
    ("load_plugin", "src.plugins.tic_tac_toe"),
    ("load_plugin", "src.plugins.coc_keeper"),
    ("load_plugin", "nonebot_plugin_suggarchat"),
    ("load_plugin", "src.plugins.ai_config_console"),
]

# 这些插件名必须出现在已加载列表里（load_plugin 失败只写日志、不抛异常，只能靠名单判断）
# 注：load_plugins(目录) 会把目录下的子模块各自注册成插件（config/handlers/services…），
# 因此这里只检查"真正提供命令的模块名"。
EXPECTED = {
    "rand_qinghua",
    "get_group_info",
    "sv_card",
    "tic_tac_toe",
    "coc_keeper",
    "nonebot_plugin_suggarchat",
    "ai_config_console",
}

for how, target in TARGETS:
    try:
        getattr(nonebot, how)(target)
        print(f"  → {how}: {target}")
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ {how}: {target} 抛异常: {e!r}")

loaded = {p.name for p in nonebot.get_loaded_plugins()}
missing = sorted(EXPECTED - loaded)

print(f"\n已加载插件 {len(loaded)} 个：{sorted(loaded)}")

if missing:
    print(f"\n❌ 缺失 {len(missing)} 个插件：{missing}")
    print("（NoneBot 对 load_plugin 的 import 失败只记日志不抛异常，请查看上方日志）")
    sys.exit(1)

print("\n===== 期望插件全部加载成功 =====")
sys.exit(0)
