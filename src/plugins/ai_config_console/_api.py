"""ai_config_console - API 路由。

挂载到 NoneBot2 的 FastAPI server_app，前缀 /ai-config/api。
所有路由经 _auth.require_token 鉴权。
"""

from fastapi import APIRouter, Depends, HTTPException

from . import _config_store, _prompt_store, _usage
from ._auth import require_token
from ._models import (
    SCENES,
    BackupResp,
    ConfigUpdateReq,
    ConfigUpdateResp,
    OkResp,
    PromptGetResp,
    PromptListItem,
    PromptListResp,
    PromptPutReq,
    StatusResp,
    UsageResp,
)

# 无前缀路由，挂载时统一加 /ai-config/api
router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/status", response_model=StatusResp, tags=["system"])
async def status() -> StatusResp:
    """系统状态。"""
    suggarchat_loaded = False
    try:
        from nonebot import get_loaded_plugins

        for p in get_loaded_plugins():
            if p.name == "nonebot_plugin_suggarchat":
                suggarchat_loaded = True
                break
    except Exception:
        pass
    return StatusResp(suggarchat_loaded=suggarchat_loaded)


@router.get("/config", response_model=dict, tags=["config"])
async def get_config() -> dict:
    """读取全量配置（api_key 打码，只读字段 editable=false）。"""
    try:
        return _config_store.get_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取配置失败: {e}")


@router.put("/config", response_model=ConfigUpdateResp, tags=["config"])
async def put_config(req: ConfigUpdateReq) -> ConfigUpdateResp:
    """保存配置（部分更新，原子写 + 备份 + 热重载）。"""
    try:
        payload = req.model_dump(exclude_none=True)
        backup_path = _config_store.update_config(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"保存配置失败: {e}")
    return ConfigUpdateResp(ok=True, backup_path=str(backup_path))


@router.get("/prompts/{scene}", response_model=PromptListResp, tags=["prompts"])
async def list_prompts(scene: str) -> PromptListResp:
    """人格列表。"""
    if scene not in SCENES:
        raise HTTPException(status_code=400, detail="场景必须是 group/private")
    items = [_prompt_store.list_prompts(scene)]
    # list_prompts 返回 list[dict]，转换为模型
    return PromptListResp(
        scene=scene,
        prompts=[PromptListItem(**i) for i in items[0]],
    )


@router.get("/prompts/{scene}/{name}", response_model=PromptGetResp, tags=["prompts"])
async def get_prompt(scene: str, name: str) -> PromptGetResp:
    """单个人格内容。"""
    if scene not in SCENES:
        raise HTTPException(status_code=400, detail="场景必须是 group/private")
    try:
        content = _prompt_store.get_prompt(scene, name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PromptGetResp(name=name, content=content)


@router.put("/prompts/{scene}/{name}", response_model=OkResp, tags=["prompts"])
async def save_prompt(scene: str, name: str, req: PromptPutReq) -> OkResp:
    """新建/覆盖人格。"""
    if scene not in SCENES:
        raise HTTPException(status_code=400, detail="场景必须是 group/private")
    try:
        _prompt_store.save_prompt(scene, name, req.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return OkResp(ok=True, message=f"人格 {scene}/{name} 已保存")


@router.delete("/prompts/{scene}/{name}", response_model=OkResp, tags=["prompts"])
async def delete_prompt(scene: str, name: str) -> OkResp:
    """删除人格（删除前备份）。"""
    if scene not in SCENES:
        raise HTTPException(status_code=400, detail="场景必须是 group/private")
    try:
        _prompt_store.delete_prompt(scene, name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return OkResp(ok=True, message=f"人格 {scene}/{name} 已删除")


@router.get("/usage", response_model=UsageResp, tags=["usage"])
async def get_usage(days: int = 7) -> UsageResp:
    """用量统计（近 N 天，含 token 与次数）。"""
    daily = _usage.get_usage(days)
    return UsageResp(days=days, daily=daily)


@router.post("/backup", response_model=BackupResp, tags=["backup"])
async def backup() -> BackupResp:
    """手动备份 config.toml。"""
    try:
        path = _config_store.backup_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"备份失败: {e}")
    return BackupResp(ok=True, backup_path=str(path))
