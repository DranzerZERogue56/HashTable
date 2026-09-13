"""The rules of Go, as text: no UI framework imports.

Kept out of app.py so the wording can be checked by a test and edited
without touching the screen that renders it, the same split layout.py and
skin.py follow.

These describe the rules *this app actually enforces*, not Go in general,
which is not quite the same thing — rule sets differ on repetition and on
how the final score is counted, and the differences are exactly the ones a
beginner trips over. Where a choice was made, the text says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

__all__ = ["Section", "SECTIONS", "title_of"]


@dataclass(frozen=True)
class Section:
    title: str
    paragraphs: Tuple[str, ...]


def title_of(index: int) -> str:
    return SECTIONS[index].title


SECTIONS: Tuple[Section, ...] = (
    Section(
        "The idea",
        (
            "Two players, Black and White, take turns placing stones on a "
            "grid. Black plays first.",
            "The aim is to end up controlling more of the board than your "
            "opponent: the points your stones sit on, plus the empty points "
            "they surround.",
        ),
    ),
    Section(
        "Placing a stone",
        (
            "Stones go on the intersections of the lines, not in the squares "
            "— including the intersections on the edges and in the corners.",
            "A stone never moves once it is placed. The only way it leaves "
            "the board is by being captured.",
        ),
    ),
    Section(
        "Liberties and capture",
        (
            "The empty points directly next to a stone — up, down, left and "
            "right, never diagonally — are its liberties.",
            "Stones of the same colour that sit next to each other along "
            "those lines form a group, and the group shares all of its "
            "liberties. A group lives as long as it has at least one.",
            "When your opponent fills the last liberty of one of your "
            "groups, the whole group is captured and taken off the board at "
            "once, however large it is.",
            "This is the part worth seeing rather than reading. Tap Show me "
            "on a board at the top of this page and step through it.",
        ),
    ),
    Section(
        "The two moves you cannot play",
        (
            "You may not play a stone that would leave its own group with no "
            "liberties. The exception is when the same move captures: taking "
            "the opponent's stones off empties the points they were on, and "
            "those become your liberties, so the move is legal.",
            "You may not repeat a position. Without that rule a single stone "
            "could be captured back and forth forever — the situation called "
            "ko. This app uses the strict form (positional superko): any "
            "position that has already appeared in the game cannot be made "
            "again, which covers ko and the rarer long repetitions too.",
            "Tapping an illegal point does nothing. Turning on Show moves "
            "marks every point you are allowed to play, so the illegal ones "
            "are the gaps.",
        ),
    ),
    Section(
        "Passing, and the end",
        (
            "You may pass instead of playing a stone, and you will want to "
            "once every move left would only fill in your own territory.",
            "Two passes in a row end the game and move on to scoring.",
            "You can also resign, which ends the game immediately and gives "
            "the win to your opponent regardless of the position.",
        ),
    ),
    Section(
        "Marking dead stones",
        (
            "After two passes, stones that are trapped and could not escape "
            "capture are simply agreed to be dead rather than played out.",
            "Tap any stone to mark its whole group dead; tap it again to "
            "change your mind. Dead stones are removed before the score is "
            "counted, so the points they stand on go to the surrounding "
            "player. Tap Done when the board is settled.",
        ),
    ),
    Section(
        "How the score is counted",
        (
            "This app uses area scoring. Your score is the number of points "
            "your stones occupy, plus the empty points surrounded by your "
            "stones alone. Empty points that both colours reach count for "
            "neither.",
            "Captured stones are not added to your score. They matter only "
            "because removing them frees the points underneath — so the "
            "capture count shown while you play is information, not part of "
            "the total.",
            "White is given komi, a fixed compensation for playing second: "
            "7.5 points by default. The half point also means the game "
            "cannot end level.",
        ),
    ),
    Section(
        "Handicap",
        (
            "A weaker player can take Black and start with a handicap: 2 to "
            "9 stones already placed on the star points, after which White "
            "plays first.",
            "Roughly one stone makes up for one rank of difference. Set it "
            "on the New game screen.",
        ),
    ),
    Section(
        "Playing on a phone",
        (
            "Placing a stone takes two taps. The first shows a translucent "
            "stone with a red ring around it; the second, on the same point, "
            "plays it. Tap somewhere else to move the preview, or Cancel to "
            "drop it. A fingertip covers several intersections and a stone "
            "cannot be taken back, so nothing is played by accident.",
            "The small red dot marks the last stone played.",
            "Show moves puts a green dot on every legal point for the side "
            "to move. On an open board that is nearly everywhere — what it "
            "is really showing you is where you may not play.",
        ),
    ),
    Section(
        "Where to go next",
        (
            "Nine by nine is the right size to learn on: a game takes a few "
            "minutes and the whole board is one fight. Thirteen by thirteen "
            "next, then the full nineteen.",
            "The one idea worth reading about after these rules is life and "
            "death — why a group with two separate eyes can never be "
            "captured. Everything else in Go is built on it.",
        ),
    ),
)
