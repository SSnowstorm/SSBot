"""ai_config_console - 用量统计（db.sqlite3 只读）。

数据源：suggarchat_global_insights 表（按日聚合 token_input/token_output/usage_count）。
连接使用只读模式（mode=ro），绝不写库。
"""

import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "nonebot_plugin_orm" / "db.sqlite3"

DB_URI = f"file:{DB_PATH.as_posix()}?mode=ro"


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_URI, uri=True)


def get_usage(days: int = 7) -> list[dict]:
    """查询近 N 天用量（含今天，按日期倒序）。表不存在/无数据时返回空。"""
    days = max(1, min(days, 90))  # 限制 1~90 天
    start = (date.today() - timedelta(days=days - 1)).isoformat()

    # 预填日期序列（保证无数据的日期也出现在结果里）
    result = []
    for i in range(days):
        d = (date.today() - timedelta(days=days - 1 - i)).isoformat()
        result.append({"date": d, "count": 0, "token_input": 0, "token_output": 0})

    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT date, token_input, token_output, usage_count "
            "FROM suggarchat_global_insights WHERE date >= ? ORDER BY date",
            (start,),
        )
        for row in cur.fetchall():
            for item in result:
                if item["date"] == row[0]:
                    item["count"] = row[3]
                    item["token_input"] = row[1]
                    item["token_output"] = row[2]
                    break
        conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        # 表不存在或数据库不可读 → 返回全零序列
        pass
    return result
