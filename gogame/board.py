"""Board state, group/liberty computation, capture resolution, Zobrist
hashing, and basic (superko-unaware) legal move generation.

This module has zero dependency on pygame or any other part of the
package: it implements the Tromp-Taylor rules
(https://tromp.github.io/go.html) at the single-position level. Ko/superko
requires game history and is handled one layer up, in rules.py.
"""

from __future__ import annotations

from enum import IntEnum
from functools import lru_cache
from random import Random
from typing import FrozenSet, Iterator, List, Optional, Tuple

Point = Tuple[int, int]

# Fixed seed so Zobrist hashes are reproducible across runs/processes.
_ZOBRIST_SEED = 0x676F5F7A6F627269  # arbitrary fixed constant ("go_zobri")


class Color(IntEnum):
    EMPTY = 0
    BLACK = 1
    WHITE = 2


def opponent(color: Color) -> Color:
    if color == Color.BLACK:
        return Color.WHITE
    if color == Color.WHITE:
        return Color.BLACK
    raise ValueError("opponent() is only defined for BLACK or WHITE")


class IllegalMoveError(Exception):
    """Raised when a move violates the basic (non-superko) rules."""


@lru_cache(maxsize=None)
def _zobrist_table(size: int) -> Tuple[Tuple[int, int], ...]:
    """Deterministic per-point (black_key, white_key) table for `size`.

    Cached and seeded so the same (size, point, color) always maps to the
    same 64-bit key within and across runs.
    """
    rng = Random(_ZOBRIST_SEED ^ size)
    table = []
    for _ in range(size * size):
        table.append((rng.getrandbits(64), rng.getrandbits(64)))
    return tuple(table)


class Board:
    """Immutable-by-convention board position.

    Mutating methods are private (`_set`); public methods that apply a
    move return a *new* Board rather than mutating in place. This lets
    callers (notably rules.py's superko check) cheaply probe candidate
    moves without needing to undo anything.
    """

    __slots__ = ("size", "_grid", "_zobrist")

    def __init__(self, size: int = 19, grid: Optional[List[Color]] = None):
        self.size = size
        if grid is None:
            self._grid: List[Color] = [Color.EMPTY] * (size * size)
        else:
            if len(grid) != size * size:
                raise ValueError("grid does not match size*size")
            self._grid = list(grid)
        self._zobrist: Optional[int] = None

    # -- basic access -----------------------------------------------

    def _index(self, point: Point) -> int:
        row, col = point
        return row * self.size + col

    def is_on_board(self, point: Point) -> bool:
        row, col = point
        return 0 <= row < self.size and 0 <= col < self.size

    def get(self, point: Point) -> Color:
        return self._grid[self._index(point)]

    def _set(self, point: Point, color: Color) -> None:
        self._grid[self._index(point)] = color
        self._zobrist = None  # invalidate cache

    def copy(self) -> "Board":
        new = Board(self.size, self._grid)
        new._zobrist = self._zobrist
        return new

    def neighbors(self, point: Point) -> Iterator[Point]:
        row, col = point
        candidates = ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1))
        for cand in candidates:
            if self.is_on_board(cand):
                yield cand

    def all_points(self) -> Iterator[Point]:
        for row in range(self.size):
            for col in range(self.size):
                yield (row, col)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Board):
            return NotImplemented
        return self.size == other.size and self._grid == other._grid

    def __hash__(self) -> int:
        return self.zobrist_hash()

    def __repr__(self) -> str:
        return f"Board(size={self.size}, hash={self.zobrist_hash():#x})"

    def to_ascii(self) -> str:
        chars = {Color.EMPTY: ".", Color.BLACK: "#", Color.WHITE: "O"}
        lines = []
        for row in range(self.size):
            lines.append("".join(chars[self.get((row, col))] for col in range(self.size)))
        return "\n".join(lines)

    @classmethod
    def from_ascii(cls, text: str) -> "Board":
        """Build a Board from a grid of '.', 'B', and 'W'/'O' characters.

        Convenience constructor for tests and debugging; not used by the
        rules engine itself.
        """
        chars = {".": Color.EMPTY, "B": Color.BLACK, "W": Color.WHITE, "O": Color.WHITE}
        rows = [line for line in text.strip("\n").splitlines()]
        size = len(rows)
        grid = []
        for row in rows:
            if len(row) != size:
                raise ValueError("from_ascii() requires a square grid")
            for ch in row:
                grid.append(chars[ch])
        return cls(size, grid)

    # -- hashing ------------------------------------------------------

    def zobrist_hash(self) -> int:
        if self._zobrist is None:
            table = _zobrist_table(self.size)
            h = 0
            for idx, color in enumerate(self._grid):
                if color == Color.BLACK:
                    h ^= table[idx][0]
                elif color == Color.WHITE:
                    h ^= table[idx][1]
            self._zobrist = h
        return self._zobrist

    # -- groups / liberties --------------------------------------------

    def group_at(self, point: Point) -> Tuple[FrozenSet[Point], FrozenSet[Point]]:
        """Return (stones, liberties) of the group containing `point`.

        `point` must hold a stone (BLACK or WHITE).
        """
        color = self.get(point)
        if color == Color.EMPTY:
            raise ValueError("group_at() requires a point holding a stone")
        stones = {point}
        liberties = set()
        stack = [point]
        while stack:
            current = stack.pop()
            for n in self.neighbors(current):
                n_color = self.get(n)
                if n_color == Color.EMPTY:
                    liberties.add(n)
                elif n_color == color and n not in stones:
                    stones.add(n)
                    stack.append(n)
        return frozenset(stones), frozenset(liberties)

    # -- move application ------------------------------------------------

    def try_play(
        self, point: Point, color: Color, allow_suicide: bool = False
    ) -> Optional[Tuple["Board", FrozenSet[Point]]]:
        """Attempt to play `color` at `point`.

        Returns (new_board, captured_points) if legal under the Tromp-Taylor
        procedure (place stone, remove opponent groups with no liberties,
        then remove the mover's own groups with no liberties unless that
        constitutes suicide and allow_suicide is False), else None.

        This function is superko-unaware; the caller (rules.py) is
        responsible for positional-superko filtering.
        """
        if not self.is_on_board(point):
            return None
        if self.get(point) != Color.EMPTY:
            return None

        new_board = self.copy()
        new_board._set(point, color)

        opp = opponent(color)
        captured: set = set()
        for n in new_board.neighbors(point):
            if new_board.get(n) == opp:
                stones, liberties = new_board.group_at(n)
                if not liberties:
                    captured |= stones
        for p in captured:
            new_board._set(p, Color.EMPTY)

        own_stones, own_liberties = new_board.group_at(point)
        if not own_liberties:
            if not allow_suicide:
                return None
            for p in own_stones:
                new_board._set(p, Color.EMPTY)

        return new_board, frozenset(captured)

    def play(self, point: Point, color: Color, allow_suicide: bool = False) -> Tuple["Board", FrozenSet[Point]]:
        """Like try_play but raises IllegalMoveError instead of returning None."""
        result = self.try_play(point, color, allow_suicide)
        if result is None:
            raise IllegalMoveError(f"illegal move: {point} for {color!r}")
        return result

    def place_stones(self, points: "list[Point]", color: Color) -> "Board":
        """Return a new Board with `points` set directly to `color`.

        For initial setup only (e.g. handicap placement): no capture
        resolution is performed, and `points` must currently be empty.
        """
        new_board = self.copy()
        for point in points:
            if new_board.get(point) != Color.EMPTY:
                raise ValueError(f"cannot place setup stone on occupied point {point}")
            new_board._set(point, color)
        return new_board

    def remove_stones(self, points: "list[Point]") -> "Board":
        """Return a new Board with `points` cleared to empty.

        For scoring use (e.g. removing stones marked dead before an area
        count): no capture resolution is performed, this just clears them.
        """
        new_board = self.copy()
        for point in points:
            new_board._set(point, Color.EMPTY)
        return new_board

    def legal_moves(self, color: Color, allow_suicide: bool = False) -> List[Point]:
        """Superko-unaware legal moves: empty points that are not (illegal) suicide."""
        moves = []
        for point in self.all_points():
            if self.get(point) != Color.EMPTY:
                continue
            if self.try_play(point, color, allow_suicide) is not None:
                moves.append(point)
        return moves

    # -- scoring -----------------------------------------------------

    def area_score(self) -> Tuple[int, int]:
        """Tromp-Taylor area score with no komi applied: (black_area, white_area).

        A player's area is their stones on the board plus every empty
        point reachable only through empty points to stones of their
        color alone (empty regions bordering both colors, or no color,
        score for neither).
        """
        black = 0
        white = 0
        visited = [False] * (self.size * self.size)

        for point in self.all_points():
            idx = self._index(point)
            if visited[idx]:
                continue
            color = self.get(point)
            if color == Color.BLACK:
                black += 1
                visited[idx] = True
                continue
            if color == Color.WHITE:
                white += 1
                visited[idx] = True
                continue

            # Flood-fill this empty region, tracking bordering colors.
            region = [point]
            visited[idx] = True
            borders: set = set()
            stack = [point]
            while stack:
                current = stack.pop()
                for n in self.neighbors(current):
                    n_color = self.get(n)
                    if n_color == Color.EMPTY:
                        n_idx = self._index(n)
                        if not visited[n_idx]:
                            visited[n_idx] = True
                            region.append(n)
                            stack.append(n)
                    else:
                        borders.add(n_color)

            if borders == {Color.BLACK}:
                black += len(region)
            elif borders == {Color.WHITE}:
                white += len(region)
            # else: neutral (dame) or fully empty board region -> no points

        return black, white
