import math


def board_out_put(board, side_len=0):
    if side_len == 0:
        side_length = math.sqrt(len(board))
    string = ""
    for item in range(len(board)):
        string += " " + board[item] + " "
        if (item % side_length) < (side_length - 1):
            string += "|"
        if item > 0 and (item + 1) % side_length == 0:
            string += "\n"
    return string


def check_winner(board, player):
    # 检查行
    for row in board:
        if all([cell == player for cell in row]):
            return True
    # 检查列
    for col in range(3):
        if all([board[row][col] == player for row in range(3)]):
            return True
    # 检查对角线
    if all([board[i][i] == player for i in range(3)]) or all([board[i][2 - i] == player for i in range(3)]):
        return True
    return False


# 检查平局
def check_draw(board):
    return all(([cell != "X" for row in board for cell in row]) or ([cell != "O" for row in board for cell in row]))


def game_start(sequence):
    print(sequence)
    res = board_out_put(sequence)
    print(res)


if __name__ == "__main__":
    sequence = [str(_) for _ in range(1, 10)]
    game_start(sequence)
