import asyncio
import random


class TicTacToe:
    def __init__(self, player1, player2=None):
        self.board = ['1', '2', '3', '4', '5', '6', '7', '8', '9']
        self.player1 = player1
        self.player2 = player2 if player2 else "Server"
        self.current_player = player1
        self.symbols = {player1: 'O', self.player2: 'X'}
        self.stop_game = False

    def print_board(self):
        for i in range(0, 9, 3):
            print(" | ".join(self.board[i:i + 3]))
            if i < 6:
                print("-" * 9)

    def check_winner(self):
        winning_combinations = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],  # Rows
            [0, 3, 6], [1, 4, 7], [2, 5, 8],  # Columns
            [0, 4, 8], [2, 4, 6]  # Diagonals
        ]
        for combo in winning_combinations:
            if self.board[combo[0]] == self.board[combo[1]] == self.board[combo[2]]:
                return self.board[combo[0]]
        return None

    def is_draw(self):
        return all([spot in ['O', 'X'] for spot in self.board])

    async def player_move(self, player):
        while not self.stop_game:
            move = input(f"{player} ({self.symbols[player]}), enter your move (1-9) or 'stop' to end the game: ")
            if move.lower() == 'stop':
                self.stop_game = True
                print(f"{player} has ended the game.")
                return
            if move.isdigit() and 1 <= int(move) <= 9:
                move = int(move) - 1
                if self.board[move] not in ['O', 'X']:
                    self.board[move] = self.symbols[player]
                    break
                else:
                    print("This spot is already taken. Try again.")
            else:
                print("Invalid input. Please enter a number between 1 and 9.")

    async def server_move(self):
        await asyncio.sleep(1)  # Simulate thinking time
        while not self.stop_game:
            move = random.randint(0, 8)
            if self.board[move] not in ['O', 'X']:
                self.board[move] = self.symbols[self.player2]
                print(f"Server ({self.symbols[self.player2]}) has made a move.")
                break

    async def game_loop(self, timeout):
        while not self.stop_game:
            self.print_board()
            if self.current_player == self.player1:
                try:
                    await asyncio.wait_for(self.player_move(self.player1), timeout=timeout)
                except asyncio.TimeoutError:
                    print(f"Time's up! {self.player1} took too long to move.")
                    self.stop_game = True
            else:
                if self.player2 == "Server":
                    await self.server_move()
                else:
                    try:
                        await asyncio.wait_for(self.player_move(self.player2), timeout=timeout)
                    except asyncio.TimeoutError:
                        print(f"Time's up! {self.player2} took too long to move.")
                        self.stop_game = True

            if self.stop_game:
                break

            winner = self.check_winner()
            if winner:
                self.print_board()
                print(f"{winner} wins!")
                break
            if self.is_draw():
                self.print_board()
                print("It's a draw!")
                break

            self.current_player = self.player1 if self.current_player == self.player2 else self.player2

    def stop(self):
        self.stop_game = True


async def main():
    player1 = input("Enter Player 1 name: ")
    mode = input("Enter '1' for single player or '2' for two players: ")
    if mode == '1':
        game = TicTacToe(player1)
    else:
        player2 = input("Enter Player 2 name: ")
        game = TicTacToe(player1, player2)

    timeout = int(input("Enter move timeout in seconds: "))
    await game.game_loop(timeout)


if __name__ == "__main__":
    asyncio.run(main())
