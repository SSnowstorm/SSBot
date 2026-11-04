"""LLM 客户端：只做一件事——把 prompt 发出去、把文本/JSON 拿回来。

设计约束：
- 任何失败（超时、网络、格式）都返回 ``None``，由调用方回退确定性实现；
- 不在这里抛异常，也不在这里做业务判断；
- 复用 ``DEEPSEEK_API_KEY``（与 suggarchat 同一套配置）。
"""

from __future__ import annotations

import json
import os
import time

import httpx
from nonebot.log import logger


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


class LlmClient:
    """最小可用的 chat 客户端；失败静默返回 None。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        self.api_key = (api_key or os.getenv("DEEPSEEK_API_KEY", "")).strip()
        self.base_url = (base_url or os.getenv("COC_LLM_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        self.model = model or os.getenv("COC_LLM_MODEL", "deepseek-chat")
        self.timeout = float(timeout if timeout is not None else os.getenv("COC_LLM_TIMEOUT", "8"))
        self.last_latency_ms = 0

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 300,
        timeout: float | None = None,
    ) -> str | None:
        if not self.available:
            return None
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            text = (data["choices"][0]["message"]["content"] or "").strip()
            self.last_latency_ms = int((time.monotonic() - started) * 1000)
            return text or None
        except Exception as exc:  # 网络/额度/格式问题一律回退
            self.last_latency_ms = int((time.monotonic() - started) * 1000)
            logger.warning(f"[coc] LLM 调用失败（{self.last_latency_ms}ms）: {exc!r}")
            return None

    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 300,
    ) -> dict | None:
        text = await self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not text:
            return None
        try:
            data = json.loads(_strip_fence(text))
        except (TypeError, ValueError):
            logger.warning(f"[coc] LLM 返回的不是 JSON: {text[:120]!r}")
            return None
        return data if isinstance(data, dict) else None
