"""ai_config_console - SuggarChat 管理系统。

将 suggarchat 的配置（config.toml）、人格文件、用量数据收敛为统一 API，
供 Web 配置台（P3）与日常运维调用。

- API 前缀：/ai-config/api/*
- 鉴权：X-AI-Config-Token 请求头，token 启动时自动生成并打印到控制台
"""

from nonebot import get_driver, logger

from . import _guard  # noqa: F401  （导入即注册 run_preprocessor 守卫）
from . import _inject_guard  # noqa: F401  （导入即注册注入拦截钩子）
from ._auth import generate_token, set_token
from ._api import router

# 子模块以下划线开头，避免被 NoneBot 扫描为独立插件
__all__ = []

driver = get_driver()


@driver.on_startup
async def _register_routes() -> None:
    """启动时注册 API 路由（server_app 挂载）。"""
    try:
        app = driver.server_app
        app.include_router(router, prefix="/ai-config/api")
        logger.info("[ai_config_console] API 已挂载: /ai-config/api/*")
    except Exception as e:
        logger.error(f"[ai_config_console] API 挂载失败: {e}")


@driver.on_startup
async def _init_token() -> None:
    """生成访问口令并打印到控制台。"""
    token = generate_token()
    set_token(token)
    logger.info("[ai_config_console] 管理系统访问口令: {}", token)
    logger.info("[ai_config_console] 浏览器打开 http://127.0.0.1:8080/ai-config/ 使用")
