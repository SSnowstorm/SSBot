def print_board(board):
    for row in board:
        print(" | ".join(row))
        print("-" * 5)


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


def check_draw(board):
    return all([cell != " " for row in board for cell in row])


def main():
    board = [[" " for _ in range(3)] for _ in range(3)]
    players = ["X", "O"]
    current_player = 0

    while True:
        print_board(board)
        row = int(input(f"Player {players[current_player]}, enter the row (0, 1, 2): "))
        col = int(input(f"Player {players[current_player]}, enter the column (0, 1, 2): "))

        if board[row][col] == " ":
            board[row][col] = players[current_player]
        else:
            print("This cell is already taken. Try again.")
            continue

        if check_winner(board, players[current_player]):
            print_board(board)
            print(f"Player {players[current_player]} wins!")
            break

        if check_draw(board):
            print_board(board)
            print("It's a draw!")
            break

        current_player = 1 - current_player


def print_grid(b_list: list):
    count = 0
    string = ""
    for item in range(len(b_list)):
        string += " " + b_list[item] + " "
        if (item % 3) < 2:
            string += "|"
        if item > 0 and (item+1) % 3 == 0:
            string += "\n"
    print(string)




if __name__ == "__main__":
    # main()
    board = [str(_) for _ in range(1, 10)]
    print(board)
    print_grid(board)
