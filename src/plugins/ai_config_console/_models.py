"""ai_config_console - Pydantic 数据模型。

定义管理系统 API 的请求/响应结构，供 _api.py 使用。
"""

from pydantic import BaseModel, Field, field_validator

# 人格场景白名单
SCENE_GROUP = "group"
SCENE_PRIVATE = "private"
SCENES = (SCENE_GROUP, SCENE_PRIVATE)

# 人格文件名白名单：中文/字母/数字/下划线/连字符，1~50 字符
NAME_PATTERN = r"^[\w\u4e00-\u9fa5_-]{1,50}$"

# 人格内容安全兜底上限（Pydantic Field 用，防恶意超大请求；业务上限见 PROMPT_MAX_LENGTH）
CONTENT_MAX = 10000

# 人格内容业务上限（可通过环境变量 AI_PROMPT_MAX_LENGTH 配置，默认 2000）
PROMPT_MAX_LENGTH = 2000


def set_prompt_max(value: int) -> None:
    """注入人格字数上限（插件启动时由 __init__.py 读取环境变量后调用）。"""
    global PROMPT_MAX_LENGTH
    PROMPT_MAX_LENGTH = max(1, int(value))


def get_prompt_max() -> int:
    """读取当前人格字数上限。"""
    return PROMPT_MAX_LENGTH


class StatusResp(BaseModel):
    """系统状态响应。"""

    running: bool = True
    suggarchat_loaded: bool = False
    version: str = "1.0"
    prompt_max_length: int = 2000


class PromptListItem(BaseModel):
    """人格列表项。"""

    name: str
    size: int = 0
    updated: str = ""


class PromptListResp(BaseModel):
    """人格列表响应。"""

    scene: str
    prompts: list[PromptListItem] = []


class PromptGetResp(BaseModel):
    """单个人格内容响应。"""

    name: str
    content: str = ""


class PromptPutReq(BaseModel):
    """新建/覆盖人格请求体。"""

    content: str = Field(..., max_length=CONTENT_MAX)

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("人格内容不能为空")
        return v


class ConfigUpdateReq(BaseModel):
    """保存配置请求体（部分更新，仅更新 editable 字段）。"""

    basic: dict = {}
    model: dict = {}
    admin: dict = {}
    session: dict = {}
    autoreply: dict = {}
    function: dict = {}
    llm: dict = {}
    tools: dict = {}
    usage_limit: dict = {}


class ConfigUpdateResp(BaseModel):
    """保存配置响应。"""

    ok: bool = True
    backup_path: str = ""


class BackupResp(BaseModel):
    """手动备份响应。"""

    ok: bool = True
    backup_path: str = ""


class BackupItem(BaseModel):
    """备份文件项。"""

    name: str
    size: int = 0
    updated: str = ""


class BackupListResp(BaseModel):
    """备份列表响应。"""

    backups: list[BackupItem] = []


class UsageDaily(BaseModel):
    """单日用量。"""

    date: str
    count: int = 0
    token_input: int = 0
    token_output: int = 0


class UsageResp(BaseModel):
    """用量统计响应。"""

    days: int = 7
    daily: list[UsageDaily] = []


class OkResp(BaseModel):
    """通用成功响应。"""

    ok: bool = True
    message: str = ""
