from gogame.board import Board, Color


def test_group_at_single_stone():
    board = Board.from_ascii(
        ".....\n"
        ".B...\n"
        ".....\n"
        ".....\n"
        "....."
    )
    stones, liberties = board.group_at((1, 1))
    assert stones == frozenset({(1, 1)})
    assert liberties == frozenset({(0, 1), (2, 1), (1, 0), (1, 2)})


def test_group_at_connected_group():
    board = Board.from_ascii(
        ".....\n"
        ".BB..\n"
        ".....\n"
        ".....\n"
        "....."
    )
    stones, liberties = board.group_at((1, 1))
    assert stones == frozenset({(1, 1), (1, 2)})
    assert liberties == frozenset({(0, 1), (0, 2), (1, 0), (1, 3), (2, 1), (2, 2)})


def test_simple_single_stone_capture():
    board = Board.from_ascii(
        ".B...\n"
        "BWB..\n"
        ".....\n"
        ".....\n"
        "....."
    )
    result = board.try_play((2, 1), Color.BLACK)
    assert result is not None
    new_board, captured = result
    assert captured == frozenset({(1, 1)})
    assert new_board.get((1, 1)) == Color.EMPTY
    assert new_board.get((2, 1)) == Color.BLACK
    # original board is untouched (copy-on-write contract)
    assert board.get((1, 1)) == Color.WHITE


def test_multi_stone_group_capture():
    board = Board.from_ascii(
        ".BB..\n"
        "BWWB.\n"
        ".B...\n"
        ".....\n"
        "....."
    )
    result = board.try_play((2, 2), Color.BLACK)
    assert result is not None
    new_board, captured = result
    assert captured == frozenset({(1, 1), (1, 2)})
    assert new_board.get((1, 1)) == Color.EMPTY
    assert new_board.get((1, 2)) == Color.EMPTY


def test_suicide_rejected_with_flag_off():
    board = Board.from_ascii(
        ".....\n"
        "..B..\n"
        ".B.B.\n"
        "..B..\n"
        "....."
    )
    # (2,2) is empty and surrounded on all four sides by black; white has
    # nothing to capture there, so playing white there is pure suicide.
    result = board.try_play((2, 2), Color.WHITE, allow_suicide=False)
    assert result is None


def test_suicide_permitted_with_flag_on():
    board = Board.from_ascii(
        ".....\n"
        "..B..\n"
        ".B.B.\n"
        "..B..\n"
        "....."
    )
    result = board.try_play((2, 2), Color.WHITE, allow_suicide=True)
    assert result is not None
    new_board, captured = result
    assert captured == frozenset()
    # the suicided white stone is removed; black stones untouched.
    assert new_board.get((2, 2)) == Color.EMPTY
    assert new_board.get((1, 2)) == Color.BLACK
    assert new_board.get((2, 1)) == Color.BLACK
    assert new_board.get((2, 3)) == Color.BLACK
    assert new_board.get((3, 2)) == Color.BLACK


def test_legal_moves_excludes_occupied_and_suicide():
    board = Board.from_ascii(
        ".....\n"
        "..B..\n"
        ".B.B.\n"
        "..B..\n"
        "....."
    )
    moves = board.legal_moves(Color.WHITE, allow_suicide=False)
    assert (1, 2) not in moves  # occupied
    assert (2, 2) not in moves  # suicide, flag off
    moves_allowing_suicide = board.legal_moves(Color.WHITE, allow_suicide=True)
    assert (2, 2) in moves_allowing_suicide


def test_snapback_style_self_atari_capture_resolves_correctly():
    """A move that looks like self-atari is legal because captures are
    resolved before the mover's own suicide check (Tromp-Taylor order),
    and the follow-up recapture must also resolve correctly.

    White(0,1) is a lone stone whose only liberty is the corner (0,0);
    White(1,0) is a separate lone stone (diagonal to (0,1), so not the
    same group) pinned by Black(1,1) but with two liberties of its own,
    so it survives. Black playing the corner captures only White(0,1)
    and, despite looking like self-atari, ends up with exactly one
    liberty: the point it just captured.
    """
    board = Board.from_ascii(
        ".WB..\n"
        "WB...\n"
        ".....\n"
        ".....\n"
        "....."
    )
    assert board.get((0, 1)) == Color.WHITE
    assert board.get((1, 0)) == Color.WHITE
    assert board.get((0, 2)) == Color.BLACK
    assert board.get((1, 1)) == Color.BLACK

    # White(0,1) group: is it connected to White(1,0)? (0,1)-(1,0) are
    # diagonal, NOT 4-adjacent, so they are separate groups.
    # White(0,1) neighbors: (0,0)=empty[Q], (0,2)=Black, (1,1)=Black
    #   -> single liberty Q=(0,0).
    # White(1,0) neighbors: (0,0)=empty[Q], (2,0)=empty, (1,1)=Black
    #   -> liberties {Q, (2,0)} -- two liberties, so it will NOT be
    #      captured by Black's move on Q; it survives, which is fine.

    result = board.try_play((0, 0), Color.BLACK)
    assert result is not None
    after_black, captured = result
    assert captured == frozenset({(0, 1)})
    # Black's new stone at Q is a lone stone (not adjacent to (0,2) or
    # (1,1), which are diagonal) with exactly one liberty: the point it
    # just captured.
    black_group, black_liberties = after_black.group_at((0, 0))
    assert black_group == frozenset({(0, 0)})
    assert black_liberties == frozenset({(0, 1)})

    # White recaptures at (0,1): this must be legal (it gains the
    # liberty vacated by the capture) and must remove Black's lone stone.
    recapture = after_black.try_play((0, 1), Color.WHITE)
    assert recapture is not None
    after_white, recaptured = recapture
    assert recaptured == frozenset({(0, 0)})
    assert after_white.get((0, 0)) == Color.EMPTY
    assert after_white.get((0, 1)) == Color.WHITE
    assert after_white.get((1, 0)) == Color.WHITE


def test_area_score_hand_built_position():
    board = Board.from_ascii(
        ".B.W.\n"
        ".B.W.\n"
        ".B.W.\n"
        ".B.W.\n"
        ".B.W."
    )
    black, white = board.area_score()
    # Column 0 (5 empty points) is Black's territory, column 1 is 5
    # Black stones, column 2 (5 empty points) borders both colors and is
    # neutral, column 3 is 5 White stones, column 4 is White's territory.
    assert black == 10
    assert white == 10


def test_zobrist_hash_is_deterministic_and_position_sensitive():
    board_a = Board.from_ascii(
        "..B..\n.....\n.....\n.....\n....."
    )
    board_b = Board.from_ascii(
        "..B..\n.....\n.....\n.....\n....."
    )
    board_c = Board.from_ascii(
        ".....\n..B..\n.....\n.....\n....."
    )
    assert board_a.zobrist_hash() == board_b.zobrist_hash()
    assert board_a.zobrist_hash() != board_c.zobrist_hash()


def test_board_copy_is_independent():
    board = Board(9)
    board2 = board.copy()
    new_board, _ = board2.try_play((4, 4), Color.BLACK)
    assert board.get((4, 4)) == Color.EMPTY
    assert new_board.get((4, 4)) == Color.BLACK
