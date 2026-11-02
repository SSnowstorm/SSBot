"""井字棋纯逻辑（与 NoneBot 解耦，便于单元测试）。

棋盘用长度 9 的列表表示，索引 0-8 对应界面上的 1-9 号格：

    0 | 1 | 2       1 | 2 | 3
    ---------       ---------
    3 | 4 | 5   →   4 | 5 | 6
    ---------       ---------
    6 | 7 | 8       7 | 8 | 9

空格用 " " 表示，玩家执 "X"，机器人执 "O"。

修复记录（D-05）：原 _model.py 里 check_winner/check_draw 形参语义混乱
（把棋盘当成 3x3 嵌套列表又按一维遍历），board_out_put 用 math.sqrt 推断
边长，导致 9 格棋盘算出 3.0 后与 int 混用，插件本身也没被 bot.py 加载。
此处重写为纯函数实现，全部返回新对象、不修改入参。
"""

EMPTY = " "
PLAYER = "X"
BOT = "O"

# 8 条获胜线（行/列/对角）
WIN_LINES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)

# 落子优先级：中心 → 四角 → 四边
CORNERS = (0, 2, 6, 8)
SIDES = (1, 3, 5, 7)


def new_board() -> list[str]:
    """新建空棋盘。"""
    return [EMPTY] * 9


def available(board: list[str]) -> list[int]:
    """返回所有空格的下标。"""
    return [i for i, cell in enumerate(board) if cell == EMPTY]


def apply_move(board: list[str], cell: int, mark: str) -> list[str]:
    """在 cell 处落子，返回新棋盘（不修改入参）。"""
    if not 0 <= cell < 9:
        raise ValueError(f"格位越界: {cell}")
    if board[cell] != EMPTY:
        raise ValueError(f"格位 {cell + 1} 已有棋子: {board[cell]}")
    nxt = list(board)
    nxt[cell] = mark
    return nxt


def winner(board: list[str]) -> str | None:
    """返回获胜方（"X"/"O"），无人获胜返回 None。"""
    for a, b, c in WIN_LINES:
        if board[a] != EMPTY and board[a] == board[b] == board[c]:
            return board[a]
    return None


def is_draw(board: list[str]) -> bool:
    """是否平局（无空位且无人获胜）。"""
    return winner(board) is None and not available(board)


def render_board(board: list[str]) -> str:
    """渲染为文本棋盘，空格显示 1-9 号位。"""
    cells = [cell if cell != EMPTY else str(i + 1) for i, cell in enumerate(board)]
    rows = [" | ".join(cells[i:i + 3]) for i in (0, 3, 6)]
    return "\n---+---+---\n".join(rows)


def parse_cell(text: str) -> int | None:
    """把用户输入解析为格位下标（"1"→0 … "9"→8）；非法输入返回 None。

    只接受单个 1-9 字符，避免和 /jm 的"序号选择"等纯数字消息混淆。
    """
    text = (text or "").strip()
    if len(text) != 1 or text not in "123456789":
        return None
    return int(text) - 1


def _winning_cell(board: list[str], mark: str) -> int | None:
    """找出让 mark 立即获胜的空格（没有则 None）。"""
    for a, b, c in WIN_LINES:
        line = (board[a], board[b], board[c])
        if line.count(mark) == 2 and line.count(EMPTY) == 1:
            return (a, b, c)[line.index(EMPTY)]
    return None


def choose_move(board: list[str], mark: str = BOT, opponent: str = PLAYER) -> int | None:
    """机器人落子决策：能赢就赢 → 能堵就堵 → 中心 → 角 → 边。"""
    if not available(board):
        return None

    cell = _winning_cell(board, mark)
    if cell is not None:
        return cell

    cell = _winning_cell(board, opponent)
    if cell is not None:
        return cell

    if board[4] == EMPTY:
        return 4

    for cell in CORNERS:
        if board[cell] == EMPTY:
            return cell

    for cell in SIDES:
        if board[cell] == EMPTY:
            return cell

    return None
