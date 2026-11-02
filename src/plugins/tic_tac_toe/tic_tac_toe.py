"""井字棋命令处理。

命令：
    /井字棋            开始一局（需 @机器人）
    /井字棋 结束       结束当前对局（也支持 退出/取消/end/quit）
    /井字棋 1-9        对局中可直接带格位落子
    直接回复 1-9       对局中落子（其它消息一律放行，不干扰正常聊天）

对局状态保存在内存（按 群号+QQ号 隔离），10 分钟无操作自动作废。

修复记录（D-05）：原 tic_tac_toe.py 的 handle 是 `for row in 3:`（对 int 迭代，
必抛 TypeError），_model.py 的胜负判定也把一维/二维棋盘混用，且 bot.py 从未
load 该插件——README 与帮助菜单却宣称 /井字棋 可用。此处补齐可玩实现，
并在 bot.py 中注册。
"""

import time

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.rule import Rule

from . import _model as model

# 一局闲置多久作废（秒）
SESSION_TIMEOUT = 600
# 会话表上限，防止内存无限增长
MAX_SESSIONS = 500

# key: (group_id 或 None, user_id) → {"board": list[str], "ts": float}
_sessions: dict[tuple[int | None, int], dict] = {}

_STOP_WORDS = {"结束", "退出", "取消", "end", "quit", "cancel"}


def _key(event: MessageEvent) -> tuple[int | None, int]:
    """会话键：群聊按群隔离，私聊 group_id 为 None。"""
    return (getattr(event, "group_id", None), event.user_id)


def _now() -> float:
    return time.time()


def _prune() -> None:
    """清理超时会话，并在超量时淘汰最旧的会话。"""
    now = _now()
    for key in [k for k, s in _sessions.items() if now - s["ts"] > SESSION_TIMEOUT]:
        _sessions.pop(key, None)
    if len(_sessions) > MAX_SESSIONS:
        for key in sorted(_sessions, key=lambda k: _sessions[k]["ts"])[: len(_sessions) - MAX_SESSIONS]:
            _sessions.pop(key, None)


def _is_playing(event: MessageEvent) -> bool:
    """Rule：该用户在当前会话里是否有进行中的对局。"""
    _prune()
    return _key(event) in _sessions


def _render(title: str, board: list[str]) -> str:
    return f"【井字棋】{title}\n{model.render_board(board)}"


def _apply_cell(board: list[str], cell: int) -> tuple[list[str], str]:
    """玩家落子 + 机器人应手，返回 (新棋盘, 状态)。

    状态取值：player_win / bot_win / draw / ongoing
    """
    board = model.apply_move(board, cell, model.PLAYER)
    if model.winner(board) == model.PLAYER:
        return board, "player_win"
    if model.is_draw(board):
        return board, "draw"

    bot_cell = model.choose_move(board)
    if bot_cell is not None:
        board = model.apply_move(board, bot_cell, model.BOT)

    if model.winner(board) == model.BOT:
        return board, "bot_win"
    if model.is_draw(board):
        return board, "draw"
    return board, "ongoing"


async def _play(key: tuple[int | None, int], cell: int, matcher) -> None:
    """执行一次落子并发送结果。调用方保证 key 存在。"""
    session = _sessions[key]
    board = session["board"]

    if board[cell] != model.EMPTY:
        await matcher.finish(
            f"{cell + 1} 号格已经有子了，换一个吧。\n" + _render("继续", board),
            at_sender=True,
        )

    board, status = _apply_cell(board, cell)

    if status == "ongoing":
        session["board"] = board
        session["ts"] = _now()
        await matcher.finish(_render("轮到你", board), at_sender=True)

    _sessions.pop(key, None)
    title = {"player_win": "你赢了", "bot_win": "我赢了", "draw": "平局"}[status]
    await matcher.finish(_render(title, board), at_sender=True)


ttt_cmd = on_command(
    "井字棋",
    aliases={"tic_tac_toe", "井字棋游戏"},
    priority=10,
    block=True,
)

ttt_move = on_message(rule=Rule(_is_playing), priority=11, block=False)


@ttt_cmd.handle()
async def handle_start(event: MessageEvent, args: Message = CommandArg()):
    """/井字棋：开始新对局；带"结束"则退出；带 1-9 则直接在活跃对局里落子。"""
    _prune()
    text = args.extract_plain_text().strip()
    key = _key(event)

    if text.lower() in _STOP_WORDS:
        if _sessions.pop(key, None) is None:
            await ttt_cmd.finish("当前没有进行中的对局。")
        await ttt_cmd.finish("对局已结束。")

    cell = model.parse_cell(text)
    if cell is not None and key in _sessions:
        await _play(key, cell, ttt_cmd)

    if text:
        await ttt_cmd.finish(
            "用法：\n"
            "  /井字棋        开始一局（你执 X 先手）\n"
            "  /井字棋 结束   结束当前对局\n"
            "  对局中直接回复 1-9 落子"
        )

    # 新开一局：覆盖旧局（用户主动重开视为放弃上一局）
    if key in _sessions:
        logger.info(f"[tic_tac_toe] 用户 {event.user_id} 重开对局，覆盖旧局")
    _sessions[key] = {"board": model.new_board(), "ts": _now()}
    _prune()

    await ttt_cmd.finish(
        _render("对局开始", _sessions[key]["board"])
        + "\n你执 X 先手，回复 1-9 落子；发送「/井字棋 结束」可退出。",
        at_sender=True,
    )


@ttt_move.handle()
async def handle_move(event: MessageEvent):
    """对局中收到 1-9 落子；其它文本原样放行（block=False）。"""
    key = _key(event)
    if key not in _sessions:
        return

    cell = model.parse_cell(event.get_plaintext())
    if cell is None:
        return  # 非落子输入：不拦截，交给其它插件/聊天

    await _play(key, cell, ttt_move)
