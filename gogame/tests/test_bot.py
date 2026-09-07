from gogame.board import Color
from gogame.bot import HeuristicBot, is_single_point_eye
from gogame.rules import GameState, Rules


def test_self_play_full_19x19_game_terminates_legally():
    game = GameState(Rules(board_size=19))
    black = HeuristicBot(Color.BLACK, seed=1)
    white = HeuristicBot(Color.WHITE, seed=2)

    max_moves = 400
    move_count = 0
    while not game.game_over and move_count < max_moves:
        bot = black if game.to_move == Color.BLACK else white
        move = bot.select_move(game)
        if move is None:
            game.pass_move()
        else:
            game.play(move)
        move_count += 1

    assert game.game_over
    assert move_count < max_moves

    # Legal final position: every stone still on the board belongs to a
    # group with at least one liberty (play()/pass_move() would already
    # have raised on anything illegal; this is an independent re-check).
    for point in game.board.all_points():
        if game.board.get(point) != Color.EMPTY:
            _, liberties = game.board.group_at(point)
            assert liberties

    # No move in the recorded history filled that color's own
    # single-point eye at the moment it was played.
    replay = GameState(Rules(board_size=19))
    for move in game.history:
        if move.is_pass:
            replay.pass_move()
            continue
        assert not is_single_point_eye(replay.board, move.point, move.color)
        replay.play(move.point)


def test_bot_never_selects_its_own_single_point_eye():
    from gogame.board import Board

    board = Board.from_ascii(
        ".....\n"
        ".BBB.\n"
        ".B.B.\n"
        ".BBB.\n"
        "....."
    )
    game = GameState(Rules(board_size=5))
    game.board = board
    game.to_move = Color.BLACK
    bot = HeuristicBot(Color.BLACK, seed=1)
    assert is_single_point_eye(board, (2, 2), Color.BLACK)
    assert (2, 2) not in bot._candidate_moves(game)
