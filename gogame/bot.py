"""A heuristic Go engine: no search tree, no neural network.

For every legal move (minus any that would fill the bot's own
single-point eye, which is filtered out rather than merely penalized),
score it with a small set of weighted heuristics plus deterministic
jitter from a seeded RNG, and play the highest-scoring move. Pass when
the best score falls below a configurable threshold, or when the
opponent has just passed and the bot is already ahead on area score.

`Engine` is the narrow interface other move-selection strategies (a
future GTP-driven engine, say) could implement in place of
HeuristicBot; nothing in gogame relies on HeuristicBot specifically.
"""

from __future__ import annotations

from random import Random
from typing import FrozenSet, List, Optional, Protocol, Tuple

from .board import Board, Color, Point, opponent
from .rules import GameState

__all__ = ["Engine", "HeuristicBot"]


class Engine(Protocol):
    """Anything that can pick a move (or pass, via None) for a GameState."""

    def select_move(self, game: GameState) -> Optional[Point]:
        ...


def _diagonal_neighbors(board: Board, point: Point) -> List[Point]:
    row, col = point
    candidates = [(row - 1, col - 1), (row - 1, col + 1), (row + 1, col - 1), (row + 1, col + 1)]
    return [c for c in candidates if board.is_on_board(c)]


def is_single_point_eye(board: Board, point: Point, color: Color) -> bool:
    """True if playing `color` at `point` would fill its own single-point eye.

    Requires every orthogonal neighbor to be `color`, and allows at most
    one enemy-controlled diagonal in the interior (zero on an edge or
    corner) -- the standard cheap real-eye-vs-false-eye check.
    """
    if board.get(point) != Color.EMPTY:
        return False
    neighbors = list(board.neighbors(point))
    if not neighbors:
        return False
    if any(board.get(n) != color for n in neighbors):
        return False
    diagonals = _diagonal_neighbors(board, point)
    on_edge = len(neighbors) < 4
    allowed_enemy_diagonals = 0 if on_edge else 1
    enemy_diagonals = sum(1 for d in diagonals if board.get(d) == opponent(color))
    return enemy_diagonals <= allowed_enemy_diagonals


class HeuristicBot:
    CAPTURE_WEIGHT = 10.0
    ESCAPE_ATARI_WEIGHT = 8.0
    EXTEND_LIBERTIES_WEIGHT = 3.0
    ADJACENCY_BONUS = 1.0
    THIRD_FOURTH_LINE_BONUS = 0.5
    FIRST_SECOND_LINE_PENALTY = -1.0
    OPENING_MOVE_LIMIT = 40
    SEALED_TERRITORY_PENALTY = -3.0

    # Under area scoring, a rational player gets pickier as the position
    # settles: filling in dame or re-poking a resolved area is worth less
    # and less as the game goes on, since it costs a move for no change
    # in the final score. Ramping the effective pass threshold up past
    # ENDGAME_MOVE_START models that, so two non-reading heuristic bots
    # still converge on a double pass instead of "playing out" the whole
    # board move by move.
    ENDGAME_MOVE_START = 250
    ENDGAME_THRESHOLD_RAMP = 0.2

    def __init__(
        self,
        color: Color,
        strength: float = 1.0,
        pass_threshold: float = 0.0,
        seed: int = 0xC0FFEE,
    ) -> None:
        self.color = color
        self.strength = strength
        self.pass_threshold = pass_threshold
        self._rng = Random(seed)

    def select_move(self, game: GameState) -> Optional[Point]:
        if game.game_over:
            return None
        if game.to_move != self.color:
            raise ValueError("select_move() called when it is not this bot's turn")

        if self._opponent_just_passed(game) and self._is_ahead(game):
            return None

        candidates = self._candidate_moves(game)
        if not candidates:
            return None

        move_number = len(game.history)
        sealed_territory = self._sealed_own_territory_points(game.board)
        scored: List[Tuple[float, Point]] = [
            (self._score_move(game, point, move_number, sealed_territory), point)
            for point in candidates
        ]
        best_score, best_point = max(scored)
        if best_score < self._effective_pass_threshold(move_number):
            return None
        return best_point

    def _effective_pass_threshold(self, move_number: int) -> float:
        extra = max(0, move_number - self.ENDGAME_MOVE_START) * self.ENDGAME_THRESHOLD_RAMP
        return self.pass_threshold + extra

    # -- candidate generation -------------------------------------------

    def _candidate_moves(self, game: GameState) -> List[Point]:
        legal = game.legal_moves(self.color)
        return [p for p in legal if not is_single_point_eye(game.board, p, self.color)]

    # -- pass conditions --------------------------------------------------

    def _opponent_just_passed(self, game: GameState) -> bool:
        if not game.history:
            return False
        last = game.history[-1]
        return last.is_pass and last.color == opponent(self.color)

    def _is_ahead(self, game: GameState) -> bool:
        result = game.score()
        if self.color == Color.BLACK:
            return result.black > result.white
        return result.white > result.black

    # -- scoring -----------------------------------------------------

    def _score_move(
        self,
        game: GameState,
        point: Point,
        move_number: int,
        sealed_territory: FrozenSet[Point],
    ) -> float:
        board = game.board
        result = board.try_play(point, self.color, game.rules.allow_suicide)
        assert result is not None, "candidate moves must already be legal"
        new_board, captured = result

        score = 0.0
        if captured:
            score += self.CAPTURE_WEIGHT * len(captured)

        score += self.ESCAPE_ATARI_WEIGHT * self._atari_escape_value(board, new_board, point)
        score += self.EXTEND_LIBERTIES_WEIGHT * self._extension_value(board, point)

        if self._is_adjacent_to_any_stone(board, point):
            score += self.ADJACENCY_BONUS

        score += self._line_bias(board, point, move_number)

        if point in sealed_territory:
            # Under area scoring, filling in already-secure territory of
            # your own color changes nothing about the final score; it
            # only wastes a move (and can needlessly weaken shape), so
            # discourage it in favor of anything that isn't neutral.
            score += self.SEALED_TERRITORY_PENALTY

        score += self._rng.uniform(-self.strength, self.strength)
        return score

    def _sealed_own_territory_points(self, board: Board) -> FrozenSet[Point]:
        """Empty points whose connected empty region borders this bot's
        color and no opponent stones -- i.e. already-secure territory
        where playing further has no scoring value under area rules."""
        color = self.color
        opp = opponent(color)
        visited = [False] * (board.size * board.size)
        sealed: List[Point] = []

        for point in board.all_points():
            idx = point[0] * board.size + point[1]
            if visited[idx]:
                continue
            if board.get(point) != Color.EMPTY:
                visited[idx] = True
                continue

            region = [point]
            visited[idx] = True
            borders_self = False
            borders_opponent = False
            stack = [point]
            while stack:
                current = stack.pop()
                for n in board.neighbors(current):
                    n_color = board.get(n)
                    if n_color == Color.EMPTY:
                        n_idx = n[0] * board.size + n[1]
                        if not visited[n_idx]:
                            visited[n_idx] = True
                            region.append(n)
                            stack.append(n)
                    elif n_color == color:
                        borders_self = True
                    elif n_color == opp:
                        borders_opponent = True

            if borders_self and not borders_opponent:
                sealed.extend(region)

        return frozenset(sealed)

    def _atari_escape_value(self, before: Board, after: Board, point: Point) -> float:
        _new_stones, new_liberties = after.group_at(point)
        if len(new_liberties) <= 1:
            return 0.0  # still in atari (or worse); nothing was actually saved

        rescued_groups = set()
        total = 0
        for n in before.neighbors(point):
            if before.get(n) == self.color:
                stones, liberties = before.group_at(n)
                if len(liberties) == 1 and point in liberties and stones not in rescued_groups:
                    rescued_groups.add(stones)
                    total += len(stones)
        return float(total)

    def _extension_value(self, before: Board, point: Point) -> float:
        seen_groups = set()
        total = 0
        for n in before.neighbors(point):
            if before.get(n) == self.color:
                stones, liberties = before.group_at(n)
                if len(liberties) <= 2 and stones not in seen_groups:
                    seen_groups.add(stones)
                    total += len(stones)
        return float(total)

    @staticmethod
    def _is_adjacent_to_any_stone(board: Board, point: Point) -> bool:
        return any(board.get(n) != Color.EMPTY for n in board.neighbors(point))

    def _line_bias(self, board: Board, point: Point, move_number: int) -> float:
        if move_number >= self.OPENING_MOVE_LIMIT:
            return 0.0
        row, col = point
        size = board.size
        line = min(row, col, size - 1 - row, size - 1 - col) + 1
        if line in (3, 4):
            return self.THIRD_FOURTH_LINE_BONUS
        if line in (1, 2):
            return self.FIRST_SECOND_LINE_PENALTY
        return 0.0
