"""ai_config_console - Token 鉴权。

访问口令在插件启动时自动生成（secrets.token_urlsafe(16)），打印到控制台。
请求需携带请求头：X-AI-Config-Token: <token>
"""

import secrets

from fastapi import Header, HTTPException

# 运行期内存中的 token（启动时由 __init__.py 注入）
TOKEN: str = ""


def generate_token() -> str:
    """生成新的访问口令。"""
    return secrets.token_urlsafe(16)


def set_token(token: str) -> None:
    """注入 token（插件启动时调用）。"""
    global TOKEN
    TOKEN = token


def require_token(x_ai_config_token: str = Header(default="")) -> None:
    """FastAPI 依赖：校验访问口令。"""
    if not TOKEN or x_ai_config_token != TOKEN:
        raise HTTPException(status_code=401, detail="无效的访问口令")
