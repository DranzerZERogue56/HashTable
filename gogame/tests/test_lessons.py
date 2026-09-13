"""The tutorial has to agree with the rules it is teaching.

Every position in lessons.py is produced by replaying the script through
the real Board, so the captures are the engine's. What is left to check is
the annotation: that the points ringed as liberties are that group's
liberties, that a move the caption calls illegal really is refused, and
that the ko move really would repeat a position. Those are hand-authored,
and hand-authored claims about rules go stale.
"""

import pytest

from gogame import lessons
from gogame.board import Board, Color
from gogame.lessons import KO, SELF_CAPTURE


def _all_steps():
    return lessons.STEPS


def test_there_are_lessons_and_every_one_has_steps():
    assert lessons.LESSONS
    for lesson in lessons.LESSONS:
        assert lesson.title.strip()
        assert lesson.steps


def test_flattened_steps_match_the_lessons():
    assert len(lessons.STEPS) == sum(len(l.steps) for l in lessons.LESSONS)
    assert lessons.STEPS[0] is lessons.LESSONS[0].steps[0]


def test_step_numbering_is_consistent():
    for number, lesson in enumerate(lessons.LESSONS, start=1):
        for index, step in enumerate(lesson.steps, start=1):
            assert step.lesson == lesson.title
            assert step.lesson_number == number
            assert step.number == index
            assert step.total == len(lesson.steps)


def test_captions_are_prose():
    for step in _all_steps():
        assert step.caption.strip()
        assert "--" not in step.caption, step.caption
        assert "  " not in step.caption, step.caption


def test_every_board_is_the_right_size():
    for step in _all_steps():
        assert step.board.size == lessons.SIZE


# -- what the annotations claim -------------------------------------------


def test_marked_points_are_empty():
    """They ring liberties and playable points, never a stone."""
    for step in _all_steps():
        for point in step.marks:
            assert step.board.get(point) == Color.EMPTY, (step.caption, point)


def test_a_played_stone_is_on_the_board_afterwards():
    for step in _all_steps():
        if step.played is not None:
            assert step.board.get(step.played) == step.played_color


def test_captured_stones_are_gone():
    for step in _all_steps():
        for point, _color in step.captured:
            assert step.board.get(point) == Color.EMPTY, (step.caption, point)


def test_self_capture_moves_really_are_refused_by_the_board():
    found = 0
    for step in _all_steps():
        if step.reason != SELF_CAPTURE:
            continue
        found += 1
        assert step.board.try_play(step.forbidden, step.forbidden_color) is None
    assert found, "no self-capture example left in the tutorial"


def test_the_ko_move_is_legal_on_the_board_and_only_forbidden_by_repetition():
    """The distinction the caption draws. Board.try_play allows it -- it is
    an ordinary capture -- and rules.py refuses it for recreating a
    position, which is what this checks by finding that position."""
    found = 0
    for lesson in lessons.LESSONS:
        earlier = []
        for step in lesson.steps:
            if step.reason == KO:
                found += 1
                result = step.board.try_play(step.forbidden, step.forbidden_color)
                assert result is not None, "the ko move should be legal on the board"
                after, _captured = result
                assert after in earlier, "the ko move should repeat an earlier position"
            earlier.append(step.board)
    assert found, "no ko example left in the tutorial"


def test_a_forbidden_point_always_says_why():
    for step in _all_steps():
        if step.forbidden is not None:
            assert step.reason in (SELF_CAPTURE, KO)
            assert step.forbidden_color in (Color.BLACK, Color.WHITE)


# -- the specific claims each lesson makes --------------------------------


def _lesson(title_fragment):
    for lesson in lessons.LESSONS:
        if title_fragment.lower() in lesson.title.lower():
            return lesson
    raise AssertionError(f"no lesson matching {title_fragment!r}")


def test_the_liberties_lesson_rings_exactly_that_stones_liberties():
    step = _lesson("Liberties").steps[0]
    _stones, liberties = step.board.group_at((2, 2))
    assert set(step.marks) == set(liberties)
    assert len(step.marks) == 4


def test_the_capture_lesson_counts_down_to_nothing():
    """Each step rings the liberties that are actually left, so the running
    commentary ("Three left", "Two left") cannot drift from the board."""
    steps = _lesson("Capturing a stone").steps
    for step in steps[:-1]:
        _stones, liberties = step.board.group_at((2, 2))
        assert set(step.marks) == set(liberties), step.caption
    assert [len(s.marks) for s in steps[:-1]] == [4, 3, 2, 1]


def test_the_capture_lesson_ends_with_the_stone_gone():
    last = _lesson("Capturing a stone").steps[-1]
    assert last.board.get((2, 2)) == Color.EMPTY
    assert last.captured == (((2, 2), Color.BLACK),)


def test_the_group_lesson_rings_the_whole_groups_liberties():
    step = _lesson("Groups").steps[0]
    stones, liberties = step.board.group_at((2, 2))
    assert stones == frozenset({(2, 1), (2, 2)})
    assert set(step.marks) == set(liberties)
    assert len(step.marks) == 6


def test_the_group_lesson_takes_both_stones_in_one_move():
    last = _lesson("Groups").steps[-1]
    assert {point for point, _c in last.captured} == {(2, 1), (2, 2)}


def test_the_edge_lesson_shows_three_liberties_then_two():
    steps = _lesson("edge").steps
    _s, side = steps[0].board.group_at((0, 2))
    assert set(steps[0].marks) == set(side) and len(side) == 3
    _s, corner = steps[1].board.group_at((4, 0))
    assert set(steps[1].marks) == set(corner) and len(corner) == 2


def test_the_self_capture_lesson_shows_the_exception_working():
    """Same point, refused for one colour and capturing for the other --
    which is the whole point of the lesson."""
    steps = _lesson("Filling your own").steps
    refused = next(s for s in steps if s.reason == SELF_CAPTURE)
    allowed = steps[-1]
    assert refused.forbidden == (2, 2)
    assert allowed.played == (2, 2)
    assert allowed.played_color == Color.BLACK
    assert len(allowed.captured) == 4
    assert all(color == Color.WHITE for _p, color in allowed.captured)


def test_the_ko_lesson_captures_before_it_forbids_the_reply():
    steps = _lesson("Ko").steps
    take = next(s for s in steps if s.captured)
    assert take.captured == (((2, 1), Color.WHITE),)
    assert take.played == (2, 2)


def test_setup_stones_never_land_on_an_occupied_point():
    """Board.place_stones raises in that case, so importing the module at
    all is the check -- this just states it out loud."""
    assert lessons.STEPS  # import succeeded


def test_an_illegal_script_would_fail_to_compile():
    """The safety net the compile step relies on: Board.play raises rather
    than quietly producing a position the game would never allow."""
    board = Board(lessons.SIZE).place_stones([(0, 0)], Color.BLACK)
    with pytest.raises(Exception):
        board.play((0, 0), Color.WHITE)
