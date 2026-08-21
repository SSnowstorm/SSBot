"""ai_config_console - SuggarChat 管理系统。

将 suggarchat 的配置（config.toml）、人格文件、用量数据收敛为统一 API，
供 Web 配置台（P3）与日常运维调用。

- API 前缀：/ai-config/api/*
- 鉴权：X-AI-Config-Token 请求头，token 启动时自动生成并打印到控制台
"""

import os

from nonebot import get_driver, logger
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from . import _guard  # noqa: F401  （导入即注册 run_preprocessor 守卫）
from . import _inject_guard  # noqa: F401  （导入即注册注入拦截钩子）
from . import _dad_guard  # noqa: F401  （导入即注册爸爸身份注入钩子）
from ._auth import generate_token, set_token
from ._api import router
from ._models import set_prompt_max

# 子模块以下划线开头，避免被 NoneBot 扫描为独立插件
__all__ = []

driver = get_driver()

# 静态目录（P3 网页）
STATIC_DIR = Path(__file__).resolve().parent / "static"


@driver.on_startup
async def _register_routes() -> None:
    """启动时注册 API 路由与静态页（server_app 挂载）。"""
    try:
        app = driver.server_app
        app.include_router(router, prefix="/ai-config/api")
        if STATIC_DIR.is_dir():
            app.mount("/ai-config", StaticFiles(directory=STATIC_DIR, html=True), name="ai_config_console")
            logger.info("[ai_config_console] 网页已挂载: /ai-config/")
        else:
            logger.warning("[ai_config_console] static 目录不存在，网页未挂载")
    except Exception as e:
        logger.error(f"[ai_config_console] 路由挂载失败: {e}")


@driver.on_startup
async def _init_token() -> None:
    """生成访问口令并打印到控制台。"""
    token = generate_token()
    set_token(token)
    logger.info("[ai_config_console] 管理系统访问口令: {}", token)
    logger.info("[ai_config_console] 浏览器打开 http://127.0.0.1:8080/ai-config/ 使用")


@driver.on_startup
async def _init_prompt_max() -> None:
    """读取人格字数上限环境变量（默认 2000，可通过 AI_PROMPT_MAX_LENGTH 配置）。"""
    val = os.getenv("AI_PROMPT_MAX_LENGTH", "2000")
    try:
        n = int(val)
    except (TypeError, ValueError):
        n = 2000
    set_prompt_max(n)
    logger.info("[ai_config_console] 人格字数上限: {} 字", n)
