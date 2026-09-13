"""Worked examples for the tutorial: no UI framework imports.

Each lesson is a short script of beats. Compiling it replays the beats on
a real `Board`, so every position the tutorial shows is one the game's own
rules produced -- the captures are the engine's captures, not a diagram
someone drew by hand and has to keep in step. test_lessons.py checks the
rest against the engine too: that the marked liberties really are that
group's liberties, that a move called self-capture really is rejected, and
that the ko move really would repeat a position.

Everything is on a 5x5 board. Big enough for the shapes that matter,
small enough that the stones stay finger-sized on a phone.

Points are (row, col) with row 0 at the top, matching board.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from .board import Board, Color, Point

__all__ = [
    "Beat",
    "Step",
    "Lesson",
    "LESSONS",
    "STEPS",
    "SELF_CAPTURE",
    "KO",
    "SIZE",
]

SIZE = 5

# Why a `forbidden` point cannot be played. They are checked differently:
# self-capture is refused by Board itself, while a ko is a perfectly legal
# move on the board and is refused by rules.py for repeating a position.
SELF_CAPTURE = "self-capture"
KO = "ko"


@dataclass(frozen=True)
class Beat:
    """One authored step, before it is replayed onto a board."""

    caption: str
    setup: Tuple[Tuple[Color, Point], ...] = ()  # placed silently, no capture
    play: Optional[Tuple[Color, Point]] = None   # played for real, captures resolve
    marks: Tuple[Point, ...] = ()                # ringed: usually liberties
    forbidden: Optional[Tuple[Color, Point]] = None
    reason: str = ""


@dataclass(frozen=True)
class Step:
    """A compiled beat: the position to draw and what changed to get there."""

    lesson: str
    lesson_number: int      # 1-based, for "Lesson 3 of 6"
    number: int             # 1-based within the lesson
    total: int              # steps in this lesson
    caption: str
    board: Board
    played: Optional[Point] = None
    played_color: Optional[Color] = None
    captured: Tuple[Tuple[Point, Color], ...] = ()
    marks: Tuple[Point, ...] = ()
    forbidden: Optional[Point] = None
    forbidden_color: Optional[Color] = None
    reason: str = ""

    @property
    def animates(self) -> bool:
        return self.played is not None or bool(self.captured)


@dataclass(frozen=True)
class Lesson:
    title: str
    steps: Tuple[Step, ...] = field(default_factory=tuple)


# -- the scripts ----------------------------------------------------------

B, W = Color.BLACK, Color.WHITE

_LIBERTIES = (
    "Liberties",
    (
        Beat(
            "A stone's liberties are the empty points touching it along the "
            "lines. This one has four.",
            setup=((B, (2, 2)),),
            marks=((1, 2), (3, 2), (2, 1), (2, 3)),
        ),
        Beat(
            "Diagonals never count. A stone stays on the board for as long as "
            "it has at least one liberty.",
            marks=((1, 2), (3, 2), (2, 1), (2, 3)),
        ),
    ),
)

_CAPTURE = (
    "Capturing a stone",
    (
        Beat(
            "Four liberties again. Watch White take them one at a time.",
            setup=((B, (2, 2)),),
            marks=((1, 2), (3, 2), (2, 1), (2, 3)),
        ),
        Beat("Three left.", play=(W, (1, 2)), marks=((3, 2), (2, 1), (2, 3))),
        Beat("Two left.", play=(W, (2, 1)), marks=((3, 2), (2, 3))),
        Beat(
            "One left. A stone down to its last liberty is in atari — one more "
            "move and it is gone.",
            play=(W, (3, 2)),
            marks=((2, 3),),
        ),
        Beat(
            "That was the last one, so the black stone is captured and comes "
            "off the board.",
            play=(W, (2, 3)),
        ),
    ),
)

_GROUPS = (
    "Groups share liberties",
    (
        Beat(
            "Stones of one colour touching along the lines are a single group. "
            "These two share six liberties between them.",
            setup=((B, (2, 1)), (B, (2, 2))),
            marks=((1, 1), (3, 1), (2, 0), (1, 2), (3, 2), (2, 3)),
        ),
        Beat(
            "White fills five of them.",
            setup=((W, (1, 1)), (W, (3, 1)), (W, (2, 0)), (W, (1, 2)), (W, (3, 2))),
            marks=((2, 3),),
        ),
        Beat(
            "One move takes the last liberty, and the whole group comes off at "
            "once — two stones or two hundred, it makes no difference.",
            play=(W, (2, 3)),
        ),
    ),
)

_EDGE = (
    "The edge is dangerous",
    (
        Beat(
            "The board edge is not a liberty. A stone on the side has three, "
            "not four.",
            setup=((B, (0, 2)),),
            marks=((0, 1), (0, 3), (1, 2)),
        ),
        Beat(
            "In the corner it has only two.",
            setup=((B, (4, 0)),),
            marks=((3, 0), (4, 1)),
        ),
        Beat(
            "So stones near the edge are captured with fewer moves. It is also "
            "why territory is easiest to make in the corners.",
            marks=((3, 0), (4, 1)),
        ),
    ),
)

# One position, both halves of the rule. White may not fill the middle
# because its own group would be left with nothing; Black may, because the
# same move takes the white stones off and the emptied points become its
# liberties.
_SELF_CAPTURE = (
    "Filling your own last liberty",
    (
        Beat(
            "Four white stones, each with one liberty left: the empty point in "
            "the middle.",
            setup=(
                (W, (1, 2)), (W, (2, 1)), (W, (2, 3)), (W, (3, 2)),
                (B, (0, 2)), (B, (1, 1)), (B, (1, 3)), (B, (2, 0)),
                (B, (2, 4)), (B, (3, 1)), (B, (3, 3)), (B, (4, 2)),
            ),
            marks=((2, 2),),
        ),
        Beat(
            "White cannot play there. The new stone would join its four "
            "friends and the whole group would have no liberties at all. "
            "Self-capture is not allowed.",
            forbidden=(W, (2, 2)),
            reason=SELF_CAPTURE,
        ),
        Beat(
            "Black can. The same point fills White's last liberty, so all four "
            "white stones come off — and the points they leave behind become "
            "the black stone's own liberties.",
            play=(B, (2, 2)),
        ),
    ),
)

_KO = (
    "Ko: the move you cannot take back",
    (
        Beat(
            "This shape is called a ko. The white stone in the middle is down "
            "to one liberty.",
            setup=(
                (B, (1, 1)), (B, (3, 1)), (B, (2, 0)),
                (W, (2, 1)), (W, (1, 2)), (W, (3, 2)), (W, (2, 3)),
            ),
            marks=((2, 2),),
        ),
        Beat("Black takes it.", play=(B, (2, 2))),
        Beat(
            "Now Black's stone is down to one liberty, and White would like to "
            "take straight back. But that would put the board exactly as it "
            "was a move ago, and the two of them could repeat it forever.",
            forbidden=(W, (2, 1)),
            reason=KO,
            marks=((2, 1),),
        ),
        Beat(
            "So White has to play somewhere else first. If Black then fills "
            "the ko, it is over; if Black answers White's move instead, White "
            "may come back and take it.",
        ),
    ),
)

_SCRIPTS = (_LIBERTIES, _CAPTURE, _GROUPS, _EDGE, _SELF_CAPTURE, _KO)


# -- compiling ------------------------------------------------------------


def _compile(title: str, beats: Tuple[Beat, ...], lesson_number: int) -> Lesson:
    board = Board(SIZE)
    steps = []
    for index, beat in enumerate(beats, start=1):
        played: Optional[Point] = None
        played_color: Optional[Color] = None
        captured: Tuple[Tuple[Point, Color], ...] = ()

        for color, point in beat.setup:
            board = board.place_stones([point], color)

        if beat.play is not None:
            color, point = beat.play
            # Board.play raises on an illegal move, so a script that does not
            # match the rules fails at import rather than teaching something
            # the game would refuse.
            after, taken = board.play(point, color)
            captured = tuple(sorted((p, board.get(p)) for p in taken))
            board = after
            played, played_color = point, color

        forbidden = forbidden_color = None
        if beat.forbidden is not None:
            forbidden_color, forbidden = beat.forbidden

        steps.append(
            Step(
                lesson=title,
                lesson_number=lesson_number,
                number=index,
                total=len(beats),
                caption=beat.caption,
                board=board,
                played=played,
                played_color=played_color,
                captured=captured,
                marks=tuple(beat.marks),
                forbidden=forbidden,
                forbidden_color=forbidden_color,
                reason=beat.reason,
            )
        )
    return Lesson(title=title, steps=tuple(steps))


LESSONS: Tuple[Lesson, ...] = tuple(
    _compile(title, beats, number)
    for number, (title, beats) in enumerate(_SCRIPTS, start=1)
)

# Flattened, because the tutorial walks straight through from one lesson to
# the next rather than making the reader pick.
STEPS: Tuple[Step, ...] = tuple(step for lesson in LESSONS for step in lesson.steps)
