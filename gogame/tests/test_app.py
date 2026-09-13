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

from gogame import lessons, rulebook, safearea
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


# -- keeping clear of the system bars --------------------------------------


def test_safe_area_is_an_ordinary_box_when_nothing_is_in_the_way():
    area = kivy_app.SafeArea()
    assert area.padding == [0, 0, 0, 0]


def test_safe_area_pads_by_the_reported_insets(monkeypatch):
    """A Samsung in three-button mode: status bar on top, navigation bar
    below, both in pixels at the panel's real density."""
    bars = safearea.Insets(left=0, top=96, right=0, bottom=144)
    monkeypatch.setattr(kivy_app.safearea, "current", lambda: bars)
    area = kivy_app.SafeArea()
    assert area.padding == [0, 96, 0, 144]


def test_safe_area_follows_a_change_of_navigation_mode(monkeypatch):
    """Switching from three buttons to gestures shrinks the bottom bar,
    and the poll has to pick that up rather than keep the old padding."""
    bars = safearea.Insets(top=96, bottom=144)
    monkeypatch.setattr(kivy_app.safearea, "current", lambda: bars)
    area = kivy_app.SafeArea()
    assert area.padding == [0, 96, 0, 144]

    bars = safearea.Insets(top=96, bottom=72)
    area.reread()
    assert area.padding == [0, 96, 0, 72]


def test_the_app_roots_everything_inside_the_safe_area():
    app = kivy_app.GoApp(session=kivy_app.build_session(9, 7.5, 0, Color.BLACK),
                         autosave=False)
    root = app.build()
    assert isinstance(root, kivy_app.SafeArea)
    assert app.manager in root.children


def test_touches_still_land_when_the_board_is_offset_by_an_inset():
    """The safe area moves the board off the window origin. Drawing and
    hit-testing both go through _to_widget/_from_widget, so they cannot
    disagree -- but nothing proved that with a non-zero origin until now,
    and every earlier test pinned the widget at (0, 0)."""
    session = kivy_app.build_session(9, 7.5, 0, Color.BLACK)
    widget = kivy_app.BoardWidget(session)
    widget.pos = (0, 144)     # navigation bar below
    widget.size = (600, 900)  # status bar above already taken off the height

    target = (2, 6)
    x, y = widget._to_widget(*pixel_at_point(target, widget.layout))
    widget.on_touch_down(_Touch((x, y)))
    assert session.pending_point == target


# -- the animated tutorial -------------------------------------------------


def test_the_lesson_board_draws_every_step_without_complaint():
    """The one that would catch a lesson referring to a point off the board
    or a colour the renderer has no texture for."""
    board = kivy_app.LessonBoard()
    board.pos = (0, 0)
    board.size = (500, 500)
    for step in lessons.STEPS:
        board.show(step, animate=False)


def test_the_lesson_board_draws_part_way_through_an_animation():
    """Mid-step the renderer is asked for fractional sizes and alphas, and
    for stones that are on neither the old board nor the new one."""
    board = kivy_app.LessonBoard()
    board.pos = (0, 0)
    board.size = (500, 500)
    capture = next(s for s in lessons.STEPS if s.captured)
    board.show(capture, animate=False)
    for progress in (0.0, 0.2, 0.45, 0.7, 1.0):
        board.progress = progress


def test_a_step_with_nothing_moving_is_not_animated():
    board = kivy_app.LessonBoard()
    board.size = (500, 500)
    still = next(s for s in lessons.STEPS if not s.animates)
    board.show(still)
    assert board.progress == 1.0


def test_the_tutorial_starts_at_the_beginning():
    app = _built_app(kivy_app.build_session(9, 7.5, 0, Color.BLACK))
    app.show_tutorial()
    assert app.manager.current == "tutorial"
    screen = app.tutorial_screen
    assert screen.board.step is lessons.STEPS[0]
    assert screen.caption.text == lessons.STEPS[0].caption
    assert screen.back.disabled is True


def test_next_and_back_walk_the_steps():
    app = _built_app(kivy_app.build_session(9, 7.5, 0, Color.BLACK))
    app.show_tutorial()
    screen = app.tutorial_screen
    screen.next_step()
    assert screen.board.step is lessons.STEPS[1]
    assert screen.back.disabled is False
    screen.previous_step()
    assert screen.board.step is lessons.STEPS[0]


def test_back_does_nothing_at_the_first_step():
    app = _built_app(kivy_app.build_session(9, 7.5, 0, Color.BLACK))
    app.show_tutorial()
    screen = app.tutorial_screen
    screen.previous_step()
    assert screen.board.step is lessons.STEPS[0]


def test_the_last_step_offers_done_and_returns_to_the_rules():
    app = _built_app(kivy_app.build_session(9, 7.5, 0, Color.BLACK))
    app.show_tutorial()
    screen = app.tutorial_screen
    for _ in range(len(lessons.STEPS) - 1):
        screen.next_step()
    assert screen.forward.text == "Done"
    screen.next_step()
    assert app.manager.current == "rules"


def test_the_heading_names_the_lesson_and_the_step():
    app = _built_app(kivy_app.build_session(9, 7.5, 0, Color.BLACK))
    app.show_tutorial()
    screen = app.tutorial_screen
    screen.next_step()
    step = lessons.STEPS[1]
    assert step.lesson in screen.heading.text
    assert f"Step {step.number} of {step.total}" in screen.counter.text


def test_the_rules_screen_offers_the_walkthrough():
    app = _built_app(kivy_app.build_session(9, 7.5, 0, Color.BLACK))
    assert "Show me on a board" in _texts(app.rules_screen)


def test_back_from_the_tutorial_returns_to_the_rules_not_the_board():
    """It was opened from the rules, so that is where back belongs."""
    app = _built_app(kivy_app.build_session(9, 7.5, 0, Color.BLACK))
    app.show_tutorial()
    assert app._on_keyboard(None, 27) is True
    assert app.manager.current == "rules"


def test_reopening_the_tutorial_starts_over():
    app = _built_app(kivy_app.build_session(9, 7.5, 0, Color.BLACK))
    app.show_tutorial()
    app.tutorial_screen.next_step()
    app.tutorial_screen.next_step()
    app.show_tutorial()
    assert app.tutorial_screen.board.step is lessons.STEPS[0]
