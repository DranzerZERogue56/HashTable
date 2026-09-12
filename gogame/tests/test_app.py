"""Smoke tests for the Kivy layer.

Importing gogame.app creates a Kivy Window, which needs a display (in CI,
run under xvfb). Where that isn't available the whole module skips: the
logic these would exercise is covered framework-free in test_session.py
and test_layout.py, so the suite stays meaningful without a screen.
"""

import os
import sys

import pytest

os.environ.setdefault("KIVY_NO_ARGS", "1")

# Kivy's SDL2 window aborts the whole process when it cannot reach a
# display -- not via an exception we could catch -- so check for one
# before importing rather than after.
if sys.platform.startswith("linux") and not (
    os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
):
    pytest.skip("no display available for the Kivy window", allow_module_level=True)

try:
    from gogame import app as kivy_app
except Exception as exc:  # pragma: no cover - depends on the machine, not the code
    pytest.skip(f"Kivy UI unavailable: {exc}", allow_module_level=True)

from gogame import rulebook
from gogame.board import Color
from gogame.layout import pixel_at_point
from gogame.session import Phase


class _Touch:
    """Stand-in for a Kivy MotionEvent; on_touch_down only reads .pos."""

    def __init__(self, pos):
        self.pos = pos


def _widget(session, width=600, height=600):
    widget = kivy_app.BoardWidget(session)
    widget.pos = (0, 0)
    widget.size = (width, height)
    return widget


def test_rows_bottom_first_reverses_whole_rows():
    """The board's stones are lit from above; getting this backwards would
    light them from below and make them look like dents."""
    top_first = bytes([1, 1, 1, 1, 2, 2, 2, 2,
                       3, 3, 3, 3, 4, 4, 4, 4])
    assert kivy_app._rows_bottom_first(top_first, 2, 2) == bytes(
        [3, 3, 3, 3, 4, 4, 4, 4,
         1, 1, 1, 1, 2, 2, 2, 2]
    )


def test_textures_are_generated_once_and_reused():
    first = kivy_app._stone_texture(Color.BLACK)
    assert kivy_app._stone_texture(Color.BLACK) is first
    assert kivy_app._stone_texture(Color.WHITE) is not first


def test_build_session_gives_the_bot_the_other_color():
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    assert session.game.board.size == 9
    assert session.game.rules.komi == 7.5
    assert set(session.engines) == {Color.WHITE}


def test_build_session_hotseat_has_no_engines():
    session = kivy_app.build_session(13, 6.5, 0, Color.EMPTY)
    assert session.engines == {}
    assert session.game.board.size == 13


def test_build_session_watching_bots_drives_both_colors():
    session = kivy_app.build_session(9, 7.5, 0, None)
    assert set(session.engines) == {Color.BLACK, Color.WHITE}


def test_build_session_applies_handicap():
    session = kivy_app.build_session(19, 0.5, 4, Color.BLACK)
    assert session.game.handicap == 4
    assert session.to_move == Color.WHITE


def test_widget_coordinate_flip_round_trips():
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    widget = _widget(session)
    assert widget._from_widget(*widget._to_widget(120, 250)) == (120, 250)


def test_touch_on_an_intersection_previews_then_confirms():
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    widget = _widget(session)
    target = (4, 4)
    x, y = widget._to_widget(*pixel_at_point(target, widget.layout))

    widget.on_touch_down(_Touch((x, y)))
    assert session.pending_point == target
    assert session.phase == Phase.PENDING_CONFIRM
    assert session.game.board.get(target) == Color.EMPTY

    widget.on_touch_down(_Touch((x, y)))
    assert session.game.board.get(target) == Color.BLACK
    assert session.pending_point is None


def test_touch_outside_the_widget_is_ignored():
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    widget = _widget(session)
    assert widget.on_touch_down(_Touch((-50, -50))) is False
    assert session.pending_point is None


def test_redraw_runs_for_every_phase():
    session = kivy_app.build_session(9, 7.5, 0, Color.EMPTY)
    widget = _widget(session)
    widget.redraw()

    session.tap_point((2, 2))
    widget.redraw()  # pending ghost stone
    session.confirm()
    session.pass_move()
    session.pass_move()
    assert session.phase == Phase.SCORING
    session.toggle_dead((2, 2))
    widget.redraw()  # dead-stone marks

    session.finish_scoring()
    widget.redraw()


def test_redraw_handles_a_board_size_with_no_star_points():
    session = kivy_app.build_session(9, 7.5, 0, Color.EMPTY)
    session.game.board = session.game.board.__class__(11)
    widget = _widget(session)
    widget.redraw()  # must not raise on a size with no handicap table


# -- the aids row, the rules screen and the result screen -------------------


def _built_app(session):
    """A GoApp with its screens constructed but no event loop running.

    build() is what wires the ScreenManager up, and it is safe to call
    directly: the Clock interval it schedules never fires because nothing
    ticks the clock in a test.
    """
    app = kivy_app.GoApp(session=session, autosave=False)
    app.build()
    return app


def _texts(widget):
    return {child.text for child in widget.walk() if hasattr(child, "text")}


def test_aids_row_offers_hints_and_the_rules():
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    app = _built_app(session)
    assert "Show moves" in _texts(app.board_screen.aids)
    assert "Rules" in _texts(app.board_screen.aids)


def test_show_moves_label_states_what_the_tap_will_do():
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    app = _built_app(session)
    session.toggle_hints()
    app.board_screen.refresh()
    assert "Hide moves" in _texts(app.board_screen.aids)


def test_board_redraws_with_hints_switched_on():
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    session.toggle_hints()
    widget = _widget(session)
    widget.redraw()  # would raise if the hint pass were broken


def test_rules_screen_renders_every_section():
    app = _built_app(kivy_app.build_session(9, 7.5, 0, Color.BLACK))
    shown = _texts(app.rules_screen)
    for section in rulebook.SECTIONS:
        assert section.title in shown, section.title
        for paragraph in section.paragraphs:
            assert paragraph in shown, paragraph


def test_result_screen_appears_when_the_game_ends():
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    app = _built_app(session)
    assert app.manager.current == "board"
    session.resign()
    app.board_screen.refresh()
    assert app.manager.current == "result"
    assert app.result_screen.headline.text == "You lose"


def test_reviewing_the_board_is_not_bounced_back_to_the_result():
    """The announcement fires once; otherwise the next redraw drags the
    player straight out of the final position they asked to look at."""
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    app = _built_app(session)
    session.resign()
    app.board_screen.refresh()
    app.show_board()
    app.board_screen.refresh()
    assert app.manager.current == "board"


def test_result_is_announced_again_after_a_new_game_ends():
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    app = _built_app(session)
    session.resign()
    app.board_screen.refresh()
    app.start_new_game(9, 7.5, 0, Color.BLACK)
    assert app.manager.current == "board"
    app.session.resign()
    app.board_screen.refresh()
    assert app.manager.current == "result"


def test_resignation_shows_no_score_line():
    """The board was never counted, so an area score printed under
    "resigned" would read as though it were the result."""
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    app = _built_app(session)
    session.resign()
    app.board_screen.refresh()
    text = app.result_screen.breakdown.text
    assert "Captures" in text
    assert "White 7.5" not in text


def test_counted_finish_shows_both_scores():
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    app = _built_app(session)
    session.game.pass_move()
    session.game.pass_move()
    session._sync_game_over()
    session.finish_scoring()
    app.board_screen.refresh()
    assert "White 7.5" in app.result_screen.breakdown.text


def test_back_leaves_any_screen_for_the_board():
    app = _built_app(kivy_app.build_session(9, 7.5, 0, Color.BLACK))
    app.show_rules()
    assert app._on_keyboard(None, 27) is True
    assert app.manager.current == "board"
