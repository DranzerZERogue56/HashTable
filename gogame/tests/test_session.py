from gogame.board import Board, Color, opponent
from gogame.bot import HeuristicBot
from gogame.rules import GameState, Rules
from gogame.session import GameSession, Phase, compute_score_with_dead_stones


def _session(size=9, engines=None, komi=7.5):
    return GameSession(GameState(Rules(board_size=size, komi=komi)), engines=engines)


# -- placement: preview then confirm -----------------------------------


def test_first_tap_previews_without_placing_a_stone():
    session = _session()
    assert session.tap_point((4, 4))
    assert session.phase == Phase.PENDING_CONFIRM
    assert session.pending_point == (4, 4)
    assert session.game.board.get((4, 4)) == Color.EMPTY
    assert len(session.game.history) == 0


def test_second_tap_on_the_same_point_commits():
    session = _session()
    session.tap_point((4, 4))
    assert session.tap_point((4, 4))
    assert session.game.board.get((4, 4)) == Color.BLACK
    assert session.phase == Phase.PLAYING
    assert session.pending_point is None
    assert session.to_move == Color.WHITE


def test_confirm_places_the_previewed_stone():
    session = _session()
    session.tap_point((2, 3))
    assert session.confirm()
    assert session.game.board.get((2, 3)) == Color.BLACK
    assert session.phase == Phase.PLAYING


def test_tapping_elsewhere_moves_the_preview_instead_of_placing():
    session = _session()
    session.tap_point((4, 4))
    session.tap_point((2, 2))
    assert session.pending_point == (2, 2)
    assert len(session.game.history) == 0
    assert session.game.board.get((4, 4)) == Color.EMPTY


def test_cancel_clears_the_preview():
    session = _session()
    session.tap_point((4, 4))
    assert session.cancel()
    assert session.pending_point is None
    assert session.phase == Phase.PLAYING
    assert not session.cancel()  # nothing left to cancel


def test_confirm_without_a_preview_does_nothing():
    session = _session()
    assert not session.confirm()
    assert len(session.game.history) == 0


def test_tap_on_an_occupied_point_is_ignored():
    session = _session()
    session.tap_point((4, 4))
    session.confirm()
    session.tap_point((0, 0))
    session.confirm()  # White plays elsewhere
    assert not session.tap_point((4, 4))
    assert session.pending_point is None


def test_taps_are_ignored_on_the_bots_turn():
    session = _session(engines={Color.BLACK: HeuristicBot(Color.BLACK, seed=1)})
    assert not session.tap_point((4, 4))
    assert session.pending_point is None
    assert len(session.game.history) == 0


# -- pass, resign, scoring ----------------------------------------------


def test_two_passes_enter_the_scoring_phase():
    session = _session()
    assert session.pass_move()
    assert session.phase == Phase.PLAYING
    assert session.pass_move()
    assert session.phase == Phase.SCORING
    assert session.is_over


def test_pass_clears_a_pending_preview():
    session = _session()
    session.tap_point((4, 4))
    session.pass_move()
    assert session.pending_point is None
    assert session.game.board.get((4, 4)) == Color.EMPTY


def test_resign_ends_the_game_and_the_opponent_wins():
    session = _session()
    assert session.resign()
    assert session.phase == Phase.RESIGNED
    assert session.resigned_by == Color.BLACK
    assert session.winner == Color.WHITE
    assert session.is_over
    assert not session.resign()  # already over


def test_toggle_dead_marks_the_whole_group():
    session = _session()
    session.game.board = Board.from_ascii(
        ".........\n"
        ".WW......\n"
        ".........\n"
        ".........\n"
        ".........\n"
        ".........\n"
        ".........\n"
        ".........\n"
        "........."
    )
    session.pass_move()
    session.pass_move()
    assert session.phase == Phase.SCORING

    assert session.toggle_dead((1, 1))
    assert session.dead_stones == {(1, 1), (1, 2)}
    assert session.toggle_dead((1, 2))
    assert session.dead_stones == set()


def test_toggle_dead_ignores_empty_points_and_non_scoring_phases():
    session = _session()
    assert not session.toggle_dead((4, 4))  # not scoring yet
    session.pass_move()
    session.pass_move()
    assert not session.toggle_dead((4, 4))  # scoring, but empty point


def test_marking_stones_dead_changes_the_score():
    session = _session(size=5)
    session.game.board = Board.from_ascii(
        ".B.W.\n"
        ".B.W.\n"
        ".B.W.\n"
        ".B.W.\n"
        ".B.W."
    )
    session.pass_move()
    session.pass_move()
    before = session.score()
    assert before.black == 10.0

    session.toggle_dead((0, 1))  # kills the whole Black column
    after = session.score()
    assert after.black == 0.0
    assert after.white == 25.0 + 7.5
    assert session.winner == Color.WHITE


def test_finish_scoring_moves_to_finished_and_back():
    session = _session()
    session.pass_move()
    session.pass_move()
    assert session.finish_scoring()
    assert session.phase == Phase.FINISHED
    assert not session.finish_scoring()
    assert session.resume_scoring()
    assert session.phase == Phase.SCORING


def test_session_built_on_a_finished_game_starts_in_scoring():
    game = GameState(Rules(board_size=9))
    game.pass_move()
    game.pass_move()
    session = GameSession(game)
    assert session.phase == Phase.SCORING


# -- bot turns -----------------------------------------------------------


def test_bot_plays_when_it_is_its_turn():
    session = _session(engines={Color.BLACK: HeuristicBot(Color.BLACK, seed=1)})
    assert session.maybe_play_bot_move()
    assert len(session.game.history) == 1
    assert session.to_move == Color.WHITE
    assert not session.maybe_play_bot_move()  # now it's the human's turn


def test_full_bot_vs_bot_game_reaches_scoring():
    session = _session(
        engines={
            Color.BLACK: HeuristicBot(Color.BLACK, seed=1),
            Color.WHITE: HeuristicBot(Color.WHITE, seed=2),
        }
    )
    steps = 0
    while not session.is_over and steps < 400:
        session.maybe_play_bot_move()
        steps += 1
    assert session.is_over
    assert session.phase == Phase.SCORING
    assert steps < 400


# -- readouts ---------------------------------------------------------------


def test_captures_are_attributed_to_the_capturing_color():
    session = _session()
    for point in [(0, 1), (5, 5), (1, 0), (5, 6), (1, 2), (1, 1)]:
        session.tap_point(point)
        session.confirm()
    session.tap_point((2, 1))
    session.confirm()  # Black captures the White stone at (1,1)
    assert session.captures_by(Color.BLACK) == 1
    assert session.captures_by(Color.WHITE) == 0


def test_last_move_point_skips_passes():
    session = _session()
    session.tap_point((3, 3))
    session.confirm()
    assert session.last_move_point == (3, 3)
    session.pass_move()
    assert session.last_move_point == (3, 3)


def test_status_text_tracks_the_phase():
    session = _session()
    assert "Black" in session.status_text()
    session.tap_point((4, 4))
    assert session.status_text() == "Confirm your move"
    session.confirm()
    session.pass_move()  # White passes
    session.pass_move()  # Black passes -> scoring
    assert "dead" in session.status_text()
    session.finish_scoring()
    assert "wins" in session.status_text() or "Draw" in session.status_text()


def test_compute_score_with_dead_stones_matches_session_score():
    game = GameState(Rules(board_size=5, komi=0.5))
    game.board = Board.from_ascii(
        ".B.W.\n"
        ".B.W.\n"
        ".B.W.\n"
        ".B.W.\n"
        ".B.W."
    )
    result = compute_score_with_dead_stones(game, set())
    assert result.black == 10.0
    assert result.white == 10.5


# -- legal-move hints ------------------------------------------------------


def _human_session(size=9, human=Color.BLACK):
    """A session where one colour is played by a person, so hints apply."""
    game = GameState(Rules(board_size=size))
    bot = HeuristicBot(opponent(human))
    return GameSession(game, engines={opponent(human): bot})


def test_hints_are_off_until_asked_for():
    session = _human_session()
    assert session.show_hints is False
    assert session.hint_points() == ()


def test_toggling_hints_lists_the_legal_moves():
    session = _human_session()
    session.toggle_hints()
    assert session.show_hints is True
    # Everything on an empty board is legal, and nothing is off-board.
    assert len(session.hint_points()) == 81
    assert set(session.hint_points()) == set(session.game.board.all_points())


def test_hints_turn_back_off():
    session = _human_session()
    session.toggle_hints()
    session.toggle_hints()
    assert session.hint_points() == ()


def test_hints_exclude_occupied_points():
    session = _human_session()
    session.toggle_hints()
    session.tap_point((4, 4))
    session.confirm()
    session.maybe_play_bot_move()
    assert (4, 4) not in session.hint_points()


def test_hints_are_empty_when_it_is_not_the_players_turn():
    """Nothing to point at while the bot is to move."""
    session = _human_session(human=Color.WHITE)  # bot has Black, so it moves first
    session.toggle_hints()
    assert session.is_human_turn() is False
    assert session.hint_points() == ()


def test_hints_are_empty_once_the_game_is_over():
    session = _human_session()
    session.toggle_hints()
    session.game.pass_move()
    session.game.pass_move()
    session._sync_game_over()
    assert session.hint_points() == ()


def test_hint_cache_is_invalidated_when_the_board_changes():
    """The cache is keyed on the position; a stale hit would offer a move
    on a point that is now occupied."""
    session = _human_session()
    session.toggle_hints()
    first = session.hint_points()
    session.tap_point((2, 2))
    session.confirm()
    session.maybe_play_bot_move()
    second = session.hint_points()
    assert first != second
    assert (2, 2) not in second


# -- who is "you", and how the game ended -----------------------------------


def test_human_color_is_the_side_without_an_engine():
    assert _human_session(human=Color.BLACK).human_color() == Color.BLACK
    assert _human_session(human=Color.WHITE).human_color() == Color.WHITE


def test_human_color_is_undefined_for_hotseat_and_for_watching_bots():
    hotseat = GameSession(GameState(Rules(board_size=9)))
    assert hotseat.human_color() is None

    both = GameSession(
        GameState(Rules(board_size=9)),
        engines={Color.BLACK: HeuristicBot(Color.BLACK),
                 Color.WHITE: HeuristicBot(Color.WHITE)},
    )
    assert both.human_color() is None


def test_result_is_second_person_when_one_colour_is_the_player():
    session = _human_session(human=Color.BLACK)
    session.resign()  # Black, the player, resigns
    assert session.result_headline() == "You lose"
    assert session.result_detail() == "Black resigned"

    other = _human_session(human=Color.BLACK)
    other.game.pass_move()          # Black passes
    other.resign()                  # now White, the bot, resigns
    assert other.result_headline() == "You win"
    assert other.result_detail() == "White resigned"


def test_result_names_the_colour_when_there_is_no_single_player():
    hotseat = GameSession(GameState(Rules(board_size=9)))
    hotseat.resign()
    assert hotseat.result_headline() == "White wins"


def test_result_detail_counts_the_margin_in_points():
    session = _human_session()
    session.game.pass_move()
    session.game.pass_move()
    session._sync_game_over()
    session.finish_scoring()
    # Empty board: White leads by komi alone.
    assert session.result_detail() == "by 7.5 points"


def test_result_detail_uses_the_singular_for_a_one_point_margin():
    game = GameState(Rules(board_size=9, komi=1.0))
    session = GameSession(game)
    session.game.pass_move()
    session.game.pass_move()
    session._sync_game_over()
    session.finish_scoring()
    assert session.result_detail() == "by 1 point"


def test_a_level_game_is_a_draw():
    game = GameState(Rules(board_size=9, komi=0.0))
    session = GameSession(game)
    session.game.pass_move()
    session.game.pass_move()
    session._sync_game_over()
    session.finish_scoring()
    assert session.result_headline() == "Draw"
    assert session.result_detail() == "The score is level"
