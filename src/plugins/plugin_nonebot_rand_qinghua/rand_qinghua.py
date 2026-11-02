"""随机情话。

命令（需 @机器人）：/情话

修复记录：
- D-07：原实现用同步 requests 在事件循环里发请求，且没有 timeout、没有异常兜底——
  接口一慢就卡住整个 bot。现已改为 httpx.AsyncClient + 超时 + 本地兜底。
- D-07 补充（实机联调发现）：原接口 api.uomg.com 的 TLS 证书已过期，请求必失败，
  用户永远只能拿到兜底句子。现改为「多接口依次尝试」：
      uapis.cn（当前可用） → uomg（证书修好后可继续用） → 本地兜底句子。
"""

import random

import httpx
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.log import logger
from nonebot.rule import to_me

TIMEOUT_SECONDS = 5.0

UAPIS_URL = "https://uapis.cn/api/v1/saying"
UOMG_URL = "https://api.uomg.com/api/rand.qinghua?format=json"

# 全部接口不可用时的本地兜底
FALLBACK_LINES = [
    "今天也想见你，哪怕只是在消息里。",
    "你发的每一条消息，我都认真看了。",
    "风很温柔，你也是。",
    "想把今天的好心情分你一半。",
    "忙的时候记得喝口水，我在这儿等你。",
]

catch_cmd = on_command("情话", rule=to_me(), priority=10, block=True)


async def _fetch_from_uapis(client: httpx.AsyncClient) -> str:
    resp = await client.get(UAPIS_URL)
    resp.raise_for_status()
    text = (resp.json() or {}).get("text")
    if not text:
        raise ValueError("uapis 未返回 text 字段")
    return str(text).strip()


async def _fetch_from_uomg(client: httpx.AsyncClient) -> str:
    resp = await client.get(UOMG_URL)
    resp.raise_for_status()
    data = resp.json()
    if str(data.get("code")) != "1" or not data.get("content"):
        raise ValueError(f"uomg 返回异常: {data.get('msg') or data}")
    return str(data["content"]).strip()


_PROVIDERS = (
    ("uapis", _fetch_from_uapis),
    ("uomg", _fetch_from_uomg),
)


async def _fetch_qinghua() -> str:
    """按顺序尝试各接口，全部失败则抛异常由调用方兜底。"""
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        for name, fetcher in _PROVIDERS:
            try:
                return await fetcher(client)
            except Exception as e:
                errors.append(f"{name}: {e!r}")
                logger.debug(f"[rand_qinghua] 接口 {name} 不可用: {e!r}")
    raise RuntimeError("; ".join(errors) or "无可用接口")


@catch_cmd.handle()
async def rand_qinghua(event: MessageEvent):
    try:
        text = await _fetch_qinghua()
    except Exception as e:
        logger.warning(f"[rand_qinghua] 情话接口全部不可用，使用本地兜底: {e!r}")
        text = random.choice(FALLBACK_LINES)

    await catch_cmd.finish(
        Message([MessageSegment.at(event.user_id), MessageSegment.text(" " + text)])
    )
