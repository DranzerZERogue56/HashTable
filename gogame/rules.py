"""Game state machine: move history, positional superko, pass/game-end
handling, area scoring with komi, and handicap placement.

Zero dependency on any UI framework; usable headlessly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

from .board import Board, Color, IllegalMoveError, Point, opponent

__all__ = [
    "Rules",
    "Move",
    "ScoreResult",
    "GameState",
    "IllegalMoveError",
    "standard_handicap_points",
]


@dataclass(frozen=True)
class Rules:
    board_size: int = 19
    komi: float = 7.5
    allow_suicide: bool = False


@dataclass(frozen=True)
class Move:
    color: Color
    point: Optional[Point]  # None means pass
    captured: frozenset = field(default_factory=frozenset)

    @property
    def is_pass(self) -> bool:
        return self.point is None


@dataclass(frozen=True)
class ScoreResult:
    black: float
    white: float

    @property
    def winner(self) -> Optional[Color]:
        if self.black > self.white:
            return Color.BLACK
        if self.white > self.black:
            return Color.WHITE
        return None  # exact tie (possible with even integer komi)


# Standard 19x19 star points (0-indexed rows/cols), used for handicap
# placement. Ordering follows common convention: corners first, then
# edges, then center.
def standard_handicap_points(size: int, handicap: int) -> List[Point]:
    if handicap < 2:
        return []
    if size == 19:
        edge = 3
        mid = 9
        far = 15
    elif size == 13:
        edge = 3
        mid = 6
        far = 9
    elif size == 9:
        edge = 2
        mid = 4
        far = 6
    else:
        raise ValueError(f"no standard handicap point table for board size {size}")

    top_left = (edge, edge)
    top_right = (edge, far)
    bottom_left = (far, edge)
    bottom_right = (far, far)
    left_mid = (mid, edge)
    right_mid = (mid, far)
    top_mid = (edge, mid)
    bottom_mid = (far, mid)
    center = (mid, mid)

    ordered = [
        bottom_left,
        top_right,
        bottom_right,
        top_left,
        left_mid,
        right_mid,
        top_mid,
        bottom_mid,
        center,
    ]
    if handicap > 9:
        raise ValueError("standard handicap points only defined up to 9 stones")
    if handicap in (5, 7):
        # 5 and 7 stone handicaps conventionally include the center point.
        points = ordered[: handicap - 1] + [center]
    else:
        points = ordered[:handicap]
    return points


class GameState:
    """Mutable game state: current board, whose turn, and full history."""

    def __init__(self, rules: Optional[Rules] = None, handicap: int = 0):
        self.rules = rules or Rules()
        self.board = Board(self.rules.board_size)
        self.to_move: Color = Color.BLACK
        self.history: List[Move] = []
        self.consecutive_passes = 0
        self.game_over = False
        self.handicap = handicap

        if handicap >= 2:
            points = standard_handicap_points(self.rules.board_size, handicap)
            self.board = self.board.place_stones(points, Color.BLACK)
            self.to_move = Color.WHITE

        self._seen_hashes: Set[int] = {self.board.zobrist_hash()}

    # -- queries -------------------------------------------------------

    def is_legal(self, point: Point, color: Optional[Color] = None) -> bool:
        color = self.to_move if color is None else color
        if self.game_over:
            return False
        result = self.board.try_play(point, color, self.rules.allow_suicide)
        if result is None:
            return False
        new_board, _captured = result
        return new_board.zobrist_hash() not in self._seen_hashes

    def legal_moves(self, color: Optional[Color] = None) -> List[Point]:
        color = self.to_move if color is None else color
        if self.game_over:
            return []
        moves = []
        for point in self.board.legal_moves(color, self.rules.allow_suicide):
            new_board, _captured = self.board.try_play(point, color, self.rules.allow_suicide)
            if new_board.zobrist_hash() not in self._seen_hashes:
                moves.append(point)
        return moves

    # -- mutation --------------------------------------------------------

    def play(self, point: Point) -> Move:
        if self.game_over:
            raise IllegalMoveError("game is over")
        color = self.to_move
        if not self.is_on_board_point(point):
            raise IllegalMoveError(f"{point} is off the board")
        result = self.board.try_play(point, color, self.rules.allow_suicide)
        if result is None:
            raise IllegalMoveError(f"illegal move: {point}")
        new_board, captured = result
        if new_board.zobrist_hash() in self._seen_hashes:
            raise IllegalMoveError(f"move {point} violates positional superko")

        self.board = new_board
        self._seen_hashes.add(new_board.zobrist_hash())
        move = Move(color=color, point=point, captured=captured)
        self.history.append(move)
        self.consecutive_passes = 0
        self.to_move = opponent(color)
        return move

    def pass_move(self) -> Move:
        if self.game_over:
            raise IllegalMoveError("game is over")
        color = self.to_move
        move = Move(color=color, point=None)
        self.history.append(move)
        self.consecutive_passes += 1
        self.to_move = opponent(color)
        if self.consecutive_passes >= 2:
            self.game_over = True
        return move

    def is_on_board_point(self, point: Point) -> bool:
        return self.board.is_on_board(point)

    # -- scoring -----------------------------------------------------

    def score(self) -> ScoreResult:
        black_area, white_area = self.board.area_score()
        return ScoreResult(black=float(black_area), white=float(white_area) + self.rules.komi)
