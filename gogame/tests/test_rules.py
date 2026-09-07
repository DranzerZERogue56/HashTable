import pytest

from gogame.board import Board, Color, IllegalMoveError
from gogame.rules import GameState, Rules, standard_handicap_points


def test_pass_twice_ends_game():
    game = GameState(Rules(board_size=9))
    game.pass_move()
    assert not game.game_over
    game.pass_move()
    assert game.game_over


def test_pass_is_always_legal_even_with_no_stones_placed():
    game = GameState(Rules(board_size=9))
    move = game.pass_move()
    assert move.is_pass
    assert game.to_move == Color.WHITE


def test_handicap_places_expected_stone_count_and_sets_white_to_move():
    game = GameState(Rules(board_size=19), handicap=4)
    black_points = [p for p in game.board.all_points() if game.board.get(p) == Color.BLACK]
    assert len(black_points) == 4
    assert set(black_points) == set(standard_handicap_points(19, 4))
    assert game.to_move == Color.WHITE


def test_basic_ko_immediate_recapture_rejected():
    game = GameState(Rules(board_size=9))

    # Build a ko shape: Black surrounds a lone White stone at (1,1) on
    # three sides, and White separately walls off (2,1) on its other
    # three sides, so capturing there leaves the capturing stone with a
    # single liberty -- the classic ko.
    game.play((0, 1))  # B
    game.play((2, 0))  # W
    game.play((1, 0))  # B
    game.play((2, 2))  # W
    game.play((1, 2))  # B
    game.play((3, 1))  # W
    game.play((8, 8))  # B filler (keeps move parity for the shape below)
    game.play((1, 1))  # W: the stone that will be captured

    move = game.play((2, 1))  # B captures White(1,1)
    assert move.captured == frozenset({(1, 1)})
    assert game.board.get((1, 1)) == Color.EMPTY

    # The recapture is basic-legal (not suicide) but must be rejected by
    # positional superko, since it exactly recreates the position from
    # before Black's capturing move.
    assert game.board.try_play((1, 1), Color.WHITE, allow_suicide=False) is not None
    assert not game.is_legal((1, 1), Color.WHITE)
    with pytest.raises(IllegalMoveError):
        game.play((1, 1))


def test_positional_superko_rejects_long_cycle_repeat():
    """Two independent simple-ko shapes far apart on the board, fought in
    an interleaved order, produce a repeat of the position from *two*
    plies back rather than the immediately preceding one -- verifying
    that superko is checked against the full set of seen positions, not
    just the last move.

    Ko-Left (cols 0-2): Black wall (0,1),(1,0),(1,2) around a lone White
    stone at (1,1) whose only liberty is (2,1), pinned by a White wall
    at (2,0),(2,2),(3,1).

    Ko-Right (cols 6-8): the mirror image with colors swapped -- a White
    wall around a lone Black stone at (1,7) whose only liberty is (2,7).
    """
    game = GameState(Rules(board_size=9))

    setup_moves = [
        (0, 1),  # B: Ko-Left wall
        (2, 0),  # W: Ko-Left wall
        (1, 0),  # B: Ko-Left wall
        (2, 2),  # W: Ko-Left wall
        (1, 2),  # B: Ko-Left wall
        (3, 1),  # W: Ko-Left wall
        (2, 6),  # B: Ko-Right wall
        (1, 1),  # W: Ko-Left lone stone (liberty: (2,1))
        (2, 8),  # B: Ko-Right wall
        (0, 7),  # W: Ko-Right wall
        (3, 7),  # B: Ko-Right wall
        (1, 6),  # W: Ko-Right wall
        (1, 7),  # B: Ko-Right lone stone
        (1, 8),  # W: Ko-Right wall (pins Black(1,7) to liberty (2,7))
    ]
    for point in setup_moves:
        game.play(point)

    left_capture = game.play((2, 1))  # Black captures Ko-Left's White stone
    assert left_capture.captured == frozenset({(1, 1)})

    right_capture = game.play((2, 7))  # White captures Ko-Right's Black stone
    assert right_capture.captured == frozenset({(1, 7)})

    # Black reversing Ko-Right would recreate the position from right
    # after the Ko-Left capture (two plies back), not the position that
    # immediately preceded this move.
    assert game.board.try_play((1, 7), Color.BLACK, allow_suicide=False) is not None
    assert not game.is_legal((1, 7), Color.BLACK)
    with pytest.raises(IllegalMoveError):
        game.play((1, 7))


def test_area_score_applies_komi_from_hand_built_position():
    game = GameState(Rules(board_size=5, komi=7.5))
    game.board = Board.from_ascii(
        ".B.W.\n"
        ".B.W.\n"
        ".B.W.\n"
        ".B.W.\n"
        ".B.W."
    )
    result = game.score()
    assert result.black == 10.0
    assert result.white == 17.5
    assert result.winner == Color.WHITE


def test_legal_moves_excludes_superko_violation():
    game = GameState(Rules(board_size=9))
    game.play((0, 1))
    game.play((2, 0))
    game.play((1, 0))
    game.play((2, 2))
    game.play((1, 2))
    game.play((3, 1))
    game.play((8, 8))
    game.play((1, 1))
    game.play((2, 1))
    assert (1, 1) not in game.legal_moves(Color.WHITE)
