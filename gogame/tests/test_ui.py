import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from gogame.board import Board, Color
from gogame.bot import HeuristicBot
from gogame.rules import GameState, Rules
from gogame.ui import (
    GoUI,
    column_label,
    compute_score_with_dead_stones,
    pixel_at_point,
    point_at_pixel,
    row_label,
)


def test_column_label_skips_i():
    assert column_label(0) == "A"
    assert column_label(7) == "H"
    assert column_label(8) == "J"  # I is skipped


def test_row_label_counts_from_bottom():
    assert row_label(0, 19) == 19  # internal row 0 (top) is displayed line 19
    assert row_label(18, 19) == 1  # internal row 18 (bottom) is displayed line 1


def test_pixel_point_round_trip():
    cell_size, margin = 30, 40
    for point in [(0, 0), (3, 15), (18, 18)]:
        pixel = pixel_at_point(point, cell_size, margin)
        assert point_at_pixel(pixel, 19, cell_size, margin) == point


def test_point_at_pixel_rejects_off_board_clicks():
    cell_size, margin = 30, 40
    # (0, 0) is well above and left of the margin -> rounds to a negative
    # row/col, outside the board entirely.
    assert point_at_pixel((0, 0), 19, cell_size, margin) is None
    # just past the last intersection on both axes
    last_center = pixel_at_point((18, 18), cell_size, margin)
    beyond = (last_center[0] + cell_size, last_center[1] + cell_size)
    assert point_at_pixel(beyond, 19, cell_size, margin) is None


def test_compute_score_with_dead_stones_removes_marked_group():
    board = Board.from_ascii(
        ".B.W.\n"
        ".B.W.\n"
        ".B.W.\n"
        ".B.W.\n"
        ".B.W."
    )
    game = GameState(Rules(board_size=5, komi=0.5))
    game.board = board
    # With nothing marked dead, this is the same split-board case from
    # earlier phases: 10 area each.
    baseline = compute_score_with_dead_stones(game, set())
    assert baseline.black == 10.0

    # Marking the whole Black column dead hands that entire side to White.
    dead = {(r, 1) for r in range(5)}
    result = compute_score_with_dead_stones(game, dead)
    assert result.black == 0.0
    assert result.white == 25.0 + 0.5


def _make_ui(size=9, engines=None):
    game = GameState(Rules(board_size=size))
    return GoUI(game, engines=engines, cell_size=24, margin=30)


def test_ui_constructs_and_draws_without_error():
    ui = _make_ui()
    ui.draw()  # must not raise


def test_human_click_places_a_legal_stone():
    ui = _make_ui()
    point = (4, 4)
    pixel = pixel_at_point(point, ui.layout.cell_size, ui.layout.margin)
    ui.handle_click(pixel)
    assert ui.game.board.get(point) == Color.BLACK
    assert ui.game.to_move == Color.WHITE


def test_click_on_bots_turn_is_ignored():
    ui = _make_ui(engines={Color.BLACK: HeuristicBot(Color.BLACK, seed=1)})
    point = (4, 4)
    pixel = pixel_at_point(point, ui.layout.cell_size, ui.layout.margin)
    ui.handle_click(pixel)
    assert ui.game.board.get(point) == Color.EMPTY
    assert len(ui.game.history) == 0


def test_pass_button_passes_for_human_turn():
    ui = _make_ui()
    ui.handle_click(ui.layout.pass_button.rect.center)
    assert len(ui.game.history) == 1
    assert ui.game.history[0].is_pass
    assert ui.game.to_move == Color.WHITE


def test_two_passes_enter_scoring_phase():
    ui = _make_ui()
    ui.handle_click(ui.layout.pass_button.rect.center)
    ui.handle_click(ui.layout.pass_button.rect.center)
    assert ui.game.game_over
    assert ui.scoring_phase
    ui.draw()  # scoring-phase rendering path must not raise


def test_resign_ends_the_game():
    ui = _make_ui()
    assert not ui.game_finished
    ui.handle_click(ui.layout.resign_button.rect.center)
    assert ui.resigned_by == Color.BLACK
    assert ui.game_finished
    ui.draw()  # resignation rendering path must not raise


def test_toggle_dead_stone_in_scoring_phase():
    ui = _make_ui()
    ui.game.play((4, 4))
    ui.game.play((0, 0))
    ui.handle_click(ui.layout.pass_button.rect.center)  # Black passes
    ui.handle_click(ui.layout.pass_button.rect.center)  # White passes -> scoring
    assert ui.scoring_phase

    pixel = pixel_at_point((4, 4), ui.layout.cell_size, ui.layout.margin)
    ui.handle_click(pixel)
    assert (4, 4) in ui.dead_stones
    ui.handle_click(pixel)
    assert (4, 4) not in ui.dead_stones


def test_done_button_exits_scoring_phase():
    ui = _make_ui()
    ui.handle_click(ui.layout.pass_button.rect.center)
    ui.handle_click(ui.layout.pass_button.rect.center)
    assert ui.scoring_phase
    ui.handle_click(ui.layout.done_button.rect.center)
    assert not ui.scoring_phase


def test_bot_plays_automatically():
    ui = _make_ui(engines={Color.BLACK: HeuristicBot(Color.BLACK, seed=1)})
    acted = ui.maybe_play_bot_move()
    assert acted
    assert len(ui.game.history) == 1
    assert ui.game.to_move == Color.WHITE


def test_full_bot_vs_bot_game_playable_end_to_end():
    ui = _make_ui(
        size=9,
        engines={
            Color.BLACK: HeuristicBot(Color.BLACK, seed=1),
            Color.WHITE: HeuristicBot(Color.WHITE, seed=2),
        },
    )
    steps = 0
    while not ui.game_finished and steps < 400:
        ui.maybe_play_bot_move()
        ui.draw()
        steps += 1
    assert ui.game_finished
    assert ui.scoring_phase
