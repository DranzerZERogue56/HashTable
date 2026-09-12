"""Interaction state machine sitting between the rules core and any UI.

Holds everything the board screen needs to decide what to draw and what
a tap means -- current phase, the pending (previewed but uncommitted)
stone, dead-stone marks, and whose turn it is -- with no dependency on
Kivy or any other framework, so it is testable without a display.

Stone placement is two-stage on purpose: the first tap previews, the
second commits. A fingertip is far wider than an intersection, and a
misplaced stone in Go cannot be taken back.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional, Set, Tuple

from .board import Color, Point, opponent
from .bot import Engine
from .rules import GameState, ScoreResult

__all__ = ["Phase", "GameSession", "compute_score_with_dead_stones"]


class Phase(Enum):
    PLAYING = "playing"
    PENDING_CONFIRM = "pending_confirm"
    SCORING = "scoring"
    FINISHED = "finished"
    RESIGNED = "resigned"


def compute_score_with_dead_stones(game: GameState, dead_stones: Set[Point]) -> ScoreResult:
    """Area score after removing stones marked dead, komi included."""
    scratch = game.board.remove_stones(list(dead_stones))
    black_area, white_area = scratch.area_score()
    return ScoreResult(black=float(black_area), white=float(white_area) + game.rules.komi)


class GameSession:
    """One game in progress, plus the UI state that goes with it.

    Every mutating method returns True if something actually changed, so
    a renderer can skip redrawing on a tap that did nothing.
    """

    def __init__(self, game: GameState, engines: Optional[Dict[Color, Engine]] = None) -> None:
        self.game = game
        self.engines: Dict[Color, Engine] = dict(engines or {})
        self.dead_stones: Set[Point] = set()
        self.pending_point: Optional[Point] = None
        self.resigned_by: Optional[Color] = None
        self.show_hints = False
        self._hint_cache: Optional[Tuple[Tuple[int, Color], Tuple[Point, ...]]] = None
        self.phase = Phase.SCORING if game.game_over else Phase.PLAYING

    # -- queries -------------------------------------------------------

    @property
    def to_move(self) -> Color:
        return self.game.to_move

    @property
    def is_over(self) -> bool:
        return self.phase in (Phase.SCORING, Phase.FINISHED, Phase.RESIGNED)

    def is_bot_turn(self) -> bool:
        return not self.is_over and self.game.to_move in self.engines

    def is_human_turn(self) -> bool:
        return not self.is_over and self.game.to_move not in self.engines

    def human_color(self) -> Optional[Color]:
        """The colour the person playing has, or None if that is not one
        colour -- hotseat, where they play both, and watching two bots."""
        humans = [c for c in (Color.BLACK, Color.WHITE) if c not in self.engines]
        return humans[0] if len(humans) == 1 else None

    @property
    def last_move_point(self) -> Optional[Point]:
        for move in reversed(self.game.history):
            if not move.is_pass:
                return move.point
        return None

    def captures_by(self, color: Color) -> int:
        return sum(len(m.captured) for m in self.game.history if m.color == color)

    def score(self) -> ScoreResult:
        if self.phase in (Phase.SCORING, Phase.FINISHED):
            return compute_score_with_dead_stones(self.game, self.dead_stones)
        return self.game.score()

    @property
    def winner(self) -> Optional[Color]:
        if self.resigned_by is not None:
            return opponent(self.resigned_by)
        return self.score().winner

    def toggle_hints(self) -> bool:
        self.show_hints = not self.show_hints
        return True

    def hint_points(self) -> Tuple[Point, ...]:
        """Legal moves for the side to move, when hints are switched on.

        Cached against the position, because enumerating them costs a
        trial play per empty intersection -- ~20 ms on a 19x19 on a
        desktop and several times that on a phone -- while the board
        redraws on every tap and every bot tick. The key includes the
        colour to move, since legality is not the same for both.

        Empty while a bot is thinking or the game is over: there is no
        move for the player to make, so there is nothing to point at.
        """
        if not self.show_hints or not self.is_human_turn():
            return ()
        key = (self.game.board.zobrist_hash(), self.to_move)
        if self._hint_cache is not None and self._hint_cache[0] == key:
            return self._hint_cache[1]
        points = tuple(self.game.legal_moves())
        self._hint_cache = (key, points)
        return points

    def status_text(self) -> str:
        if self.phase == Phase.RESIGNED:
            assert self.resigned_by is not None
            return f"{self.resigned_by.name.title()} resigned"
        if self.phase == Phase.SCORING:
            return "Tap stones to mark them dead"
        if self.phase == Phase.FINISHED:
            winner = self.winner
            return f"{winner.name.title()} wins" if winner else "Draw"
        if self.phase == Phase.PENDING_CONFIRM:
            return "Confirm your move"
        return f"{self.to_move.name.title()} to play"

    def result_headline(self) -> str:
        """Said in the second person when one colour is clearly 'you'."""
        winner = self.winner
        if winner is None:
            return "Draw"
        you = self.human_color()
        if you is None:
            return f"{winner.name.title()} wins"
        return "You win" if winner == you else "You lose"

    def result_detail(self) -> str:
        if self.resigned_by is not None:
            return f"{self.resigned_by.name.title()} resigned"
        score = self.score()
        margin = abs(score.black - score.white)
        if margin == 0:
            return "The score is level"
        return f"by {margin:g} point{'' if margin == 1 else 's'}"

    # -- placement -----------------------------------------------------

    def tap_point(self, point: Point) -> bool:
        """A tap landing on `point`. Previews, re-previews, confirms a
        repeat tap on the pending point, or toggles a dead group while
        scoring."""
        if self.phase == Phase.SCORING:
            return self.toggle_dead(point)
        if self.is_over or self.is_bot_turn():
            return False
        if point == self.pending_point:
            return self.confirm()
        if not self.game.is_legal(point):
            return False
        self.pending_point = point
        self.phase = Phase.PENDING_CONFIRM
        return True

    def confirm(self) -> bool:
        if self.phase != Phase.PENDING_CONFIRM or self.pending_point is None:
            return False
        point = self.pending_point
        self.pending_point = None
        self.phase = Phase.PLAYING
        if not self.game.is_legal(point):
            return True  # the board moved under us; the preview is simply dropped
        self.game.play(point)
        self._sync_game_over()
        return True

    def cancel(self) -> bool:
        if self.pending_point is None:
            return False
        self.pending_point = None
        if self.phase == Phase.PENDING_CONFIRM:
            self.phase = Phase.PLAYING
        return True

    # -- other actions --------------------------------------------------

    def pass_move(self) -> bool:
        if self.is_over or self.is_bot_turn():
            return False
        self.pending_point = None
        self.phase = Phase.PLAYING
        self.game.pass_move()
        self._sync_game_over()
        return True

    def resign(self) -> bool:
        if self.is_over:
            return False
        self.pending_point = None
        self.resigned_by = self.game.to_move
        self.phase = Phase.RESIGNED
        return True

    def toggle_dead(self, point: Point) -> bool:
        """Mark or unmark the whole group at `point` as dead."""
        if self.phase != Phase.SCORING:
            return False
        if self.game.board.get(point) == Color.EMPTY:
            return False
        stones, _liberties = self.game.board.group_at(point)
        if stones & self.dead_stones:
            self.dead_stones -= stones
        else:
            self.dead_stones |= stones
        return True

    def finish_scoring(self) -> bool:
        if self.phase != Phase.SCORING:
            return False
        self.phase = Phase.FINISHED
        return True

    def resume_scoring(self) -> bool:
        if self.phase != Phase.FINISHED:
            return False
        self.phase = Phase.SCORING
        return True

    def maybe_play_bot_move(self) -> bool:
        """Let the engine for the side to move play once, if there is one."""
        if self.is_over:
            return False
        engine = self.engines.get(self.game.to_move)
        if engine is None:
            return False
        move = engine.select_move(self.game)
        if move is None:
            self.game.pass_move()
        else:
            self.game.play(move)
        self._sync_game_over()
        return True

    def _sync_game_over(self) -> None:
        if self.game.game_over and self.phase not in (Phase.FINISHED, Phase.RESIGNED):
            self.pending_point = None
            self.phase = Phase.SCORING
