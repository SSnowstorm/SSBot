import os
from pathlib import Path

from dotenv import load_dotenv

# 将 env 文件变量注入 os.environ：
# - nonebot.init() 只会把变量读入配置对象，不会写入 os.environ
# - suggarchat 的 ${VAR} 占位符（如 ${DEEPSEEK_API_KEY}）从 os.environ 读取
# - 优先按 ENVIRONMENT 变量选择 .env.{ENVIRONMENT}，未设置时兜底加载 .env.dev
_env = os.environ.get("ENVIRONMENT")
_env_file = Path(f".env.{_env}") if _env else Path(".env.dev")
if _env_file.is_file():
    load_dotenv(_env_file, override=False)

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter

# 初始化 NoneBot（配置通过 .env 文件读取，不要在这里传 websocket_path）
# 显式指定 env 文件：优先 ENVIRONMENT 变量，未设置时默认 .env.dev（当前项目实际环境）
_env = os.environ.get("ENVIRONMENT")
nonebot.init(_env_file=f".env.{_env}" if _env else ".env.dev")

# 注册 OneBot V11 适配器
driver = nonebot.get_driver()
driver.register_adapter(ONEBOT_V11Adapter)

# 加载插件
nonebot.load_plugins("src/plugins/plugin_nonebot_rand_qinghua")
nonebot.load_plugins("src/plugins/jm_downloader")
nonebot.load_plugins("src/plugins/get_group_info")
nonebot.load_plugin("src.plugins.interactive_help")
nonebot.load_plugin("src.plugins.sv_card")
nonebot.load_plugin("nonebot_plugin_suggarchat")  # AI 聊天（SuggarChat）
# nonebot.load_plugins("src/plugins/plugin_nonebot_jmcomic")  # 配置路径未指定，暂不加载


# ============== 插件初始化 ==============

@nonebot.get_driver().on_startup
async def init_sv_card():
    """影之诗卡牌插件启动时加载数据。"""
    try:
        from src.plugins.sv_card._cache import init_cache, _try_register_scheduler
        await init_cache()
        _try_register_scheduler()
    except Exception as e:
        nonebot.logger.error(f"影之诗卡牌数据加载失败: {e}")

if __name__ == "__main__":
    nonebot.run()
