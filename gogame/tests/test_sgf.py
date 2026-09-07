import pytest

from gogame.board import Color
from gogame.rules import GameState, Rules
from gogame.sgf import SGFParseError, game_to_sgf, point_to_sgf, sgf_to_game, sgf_to_point


def test_point_to_sgf_and_back():
    assert point_to_sgf((0, 0)) == "aa"
    assert point_to_sgf((18, 18)) == "ss"
    assert point_to_sgf((3, 15)) == "pd"
    assert sgf_to_point("pd") == (3, 15)
    assert sgf_to_point("aa") == (0, 0)
    assert sgf_to_point("ss") == (18, 18)


def test_sgf_to_point_rejects_out_of_range_letters():
    with pytest.raises(SGFParseError):
        sgf_to_point("ta")


def test_game_to_sgf_literal_format_single_move():
    game = GameState(Rules(board_size=19, komi=7.5))
    game.play((3, 15))
    assert game_to_sgf(game) == "(;GM[1]FF[4]SZ[19]KM[7.5];B[pd])\n"


def test_game_to_sgf_literal_format_pass():
    game = GameState(Rules(board_size=9, komi=7.5))
    game.pass_move()
    assert game_to_sgf(game) == "(;GM[1]FF[4]SZ[9]KM[7.5];B[])\n"


def test_round_trip_moves_captures_and_a_mid_game_pass():
    game = GameState(Rules(board_size=9, komi=6.5))
    game.play((0, 1))
    game.play((5, 5))
    game.play((1, 0))
    game.play((5, 6))
    game.play((1, 2))
    game.play((1, 1))  # White stone that will be captured
    game.play((2, 1))  # Black captures it
    game.pass_move()  # White passes (does not end the game)
    game.play((3, 3))
    game.play((4, 4))

    text = game_to_sgf(game, black_name="Black", white_name="White", date="2024-01-01")
    replayed = sgf_to_game(text)

    assert len(replayed.history) == len(game.history)
    for original_move, replayed_move in zip(game.history, replayed.history):
        assert original_move.color == replayed_move.color
        assert original_move.point == replayed_move.point

    assert replayed.board == game.board
    assert replayed.to_move == game.to_move
    assert replayed.rules.board_size == game.rules.board_size
    assert replayed.rules.komi == game.rules.komi
    assert replayed.game_over == game.game_over


def test_round_trip_with_handicap():
    game = GameState(Rules(board_size=19, komi=0.5), handicap=4)
    game.play((2, 2))
    game.play((16, 16))

    text = game_to_sgf(game)
    assert "HA[4]" in text

    replayed = sgf_to_game(text)
    assert replayed.handicap == 4
    assert replayed.board == game.board
    assert replayed.to_move == game.to_move


def test_sgf_to_game_rejects_non_go_game_type():
    with pytest.raises(SGFParseError):
        sgf_to_game("(;GM[2]FF[4]SZ[19];B[pd])")


def test_sgf_to_game_follows_only_the_first_variation():
    text = "(;GM[1]FF[4]SZ[9];B[ee](;W[gg])(;W[cc]))"
    game = sgf_to_game(text)
    assert len(game.history) == 2
    assert game.history[1].color == Color.WHITE
    assert game.history[1].point == sgf_to_point("gg")
