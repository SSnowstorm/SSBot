# plugins/interactive_help/utils.py
"""通用工具函数。"""

import base64
import json

from nonebot.log import logger


def encode_callback(data: dict) -> str:
    """将 callback 数据编码为字符串，塞入按钮的 callback_data 字段。"""
    try:
        json_bytes = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(json_bytes).decode("utf-8").rstrip("=")
    except Exception as e:
        logger.error(f"编码 callback_data 失败: {e}")
        return ""


def decode_callback(data: str) -> dict | None:
    """解码按钮 callback_data。"""
    if not data:
        return None

    # 补齐 base64 填充
    padding_needed = 4 - (len(data) % 4)
    if padding_needed != 4:
        data += "=" * padding_needed

    try:
        json_bytes = base64.urlsafe_b64decode(data.encode("utf-8"))
        return json.loads(json_bytes.decode("utf-8"))
    except Exception as e:
        logger.warning(f"解码 callback_data 失败: {e}, raw={data[:50]}")
        return None
