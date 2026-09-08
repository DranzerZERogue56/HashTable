"""pygame board rendering and input for the Go game.

Coordinate mapping here is display-only and independent of SGF's a-s
letters (sgf.py): columns are labeled A-T skipping I, and rows are
numbered from 1 at the bottom to N at the top, matching the
conventional printed Go board -- even though internally row 0 is the
top row of the (row, col) grid used throughout the rest of the
package.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import pygame

from .bot import Engine
from .board import Color, Point, opponent
from .rules import GameState, IllegalMoveError, ScoreResult, standard_handicap_points

__all__ = ["GoUI", "compute_score_with_dead_stones", "point_at_pixel", "pixel_at_point"]

_COLUMN_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"  # skips I, per Go convention

_BACKGROUND = (220, 179, 92)
_LINE_COLOR = (40, 30, 10)
_BLACK_STONE = (20, 20, 20)
_WHITE_STONE = (245, 245, 245)
_STONE_OUTLINE = (40, 30, 10)
_LAST_MOVE_MARKER = (200, 30, 30)
_DEAD_STONE_MARK = (200, 30, 30)
_PANEL_BG = (245, 240, 225)
_TEXT_COLOR = (20, 20, 20)
_BUTTON_BG = (210, 200, 175)
_BUTTON_BORDER = (60, 50, 30)


def column_label(col: int) -> str:
    return _COLUMN_LETTERS[col]


def row_label(row: int, size: int) -> int:
    """Displayed row number: row 0 (top of the grid) is line `size`."""
    return size - row


def point_at_pixel(pos: Tuple[int, int], size: int, cell_size: int, margin: int) -> Optional[Point]:
    """Map a pixel position to the nearest board point, or None if the
    click isn't close enough to an intersection to count."""
    x, y = pos
    col = round((x - margin) / cell_size)
    row = round((y - margin) / cell_size)
    if not (0 <= row < size and 0 <= col < size):
        return None
    center_x, center_y = pixel_at_point((row, col), cell_size, margin)
    if abs(x - center_x) > cell_size // 2 or abs(y - center_y) > cell_size // 2:
        return None
    return (row, col)


def pixel_at_point(point: Point, cell_size: int, margin: int) -> Tuple[int, int]:
    row, col = point
    return margin + col * cell_size, margin + row * cell_size


def compute_score_with_dead_stones(game: GameState, dead_stones: Set[Point]) -> ScoreResult:
    """Area score after removing stones marked dead, komi included."""
    scratch = game.board.remove_stones(list(dead_stones))
    black_area, white_area = scratch.area_score()
    return ScoreResult(black=float(black_area), white=float(white_area) + game.rules.komi)


@dataclass
class _Button:
    rect: "pygame.Rect"
    label: str


@dataclass
class _Layout:
    cell_size: int
    margin: int
    board_pixels: int
    panel_x: int
    panel_width: int
    width: int
    height: int
    pass_button: _Button = field(init=False)
    resign_button: _Button = field(init=False)
    done_button: _Button = field(init=False)

    def __post_init__(self) -> None:
        button_w, button_h = self.panel_width - 40, 36
        bx = self.panel_x + 20
        self.pass_button = _Button(pygame.Rect(bx, self.height - 100, button_w, button_h), "Pass")
        self.resign_button = _Button(pygame.Rect(bx, self.height - 56, button_w, button_h), "Resign")
        self.done_button = _Button(pygame.Rect(bx, self.height - 56, button_w, button_h), "Done scoring")


class GoUI:
    """Drives one game: rendering, mouse input, and bot turns."""

    def __init__(
        self,
        game: GameState,
        engines: Optional[Dict[Color, Engine]] = None,
        cell_size: int = 32,
        margin: int = 44,
    ) -> None:
        self.game = game
        self.engines: Dict[Color, Engine] = engines or {}
        self.dead_stones: Set[Point] = set()
        self.scoring_phase = False
        self.resigned_by: Optional[Color] = None

        panel_width = 260
        board_pixels = (game.board.size - 1) * cell_size
        width = margin * 2 + board_pixels + panel_width
        height = max(margin * 2 + board_pixels, 360)
        self.layout = _Layout(
            cell_size=cell_size,
            margin=margin,
            board_pixels=board_pixels,
            panel_x=margin * 2 + board_pixels,
            panel_width=panel_width,
            width=width,
            height=height,
        )

        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        pygame.init()
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Go")
        self.font = pygame.font.SysFont(None, 22)
        self.small_font = pygame.font.SysFont(None, 18)

    # -- game-over state -------------------------------------------------

    @property
    def game_finished(self) -> bool:
        return self.game.game_over or self.resigned_by is not None

    def _enter_scoring_phase_if_needed(self) -> None:
        if self.game.game_over and self.resigned_by is None:
            self.scoring_phase = True

    # -- bot turns -----------------------------------------------------

    def maybe_play_bot_move(self) -> bool:
        """If it's a bot's turn, play (or pass) once. Returns True if it acted."""
        if self.game_finished:
            return False
        engine = self.engines.get(self.game.to_move)
        if engine is None:
            return False
        move = engine.select_move(self.game)
        if move is None:
            self.game.pass_move()
        else:
            self.game.play(move)
        self._enter_scoring_phase_if_needed()
        return True

    # -- input -----------------------------------------------------------

    def handle_click(self, pos: Tuple[int, int]) -> None:
        if self.resigned_by is not None:
            return

        if self.scoring_phase:
            if self.layout.done_button.rect.collidepoint(pos):
                self.scoring_phase = False
                return
            point = point_at_pixel(pos, self.game.board.size, self.layout.cell_size, self.layout.margin)
            if point is not None and self.game.board.get(point) != Color.EMPTY:
                if point in self.dead_stones:
                    self.dead_stones.discard(point)
                else:
                    self.dead_stones.add(point)
            return

        if self.layout.resign_button.rect.collidepoint(pos):
            self.resigned_by = self.game.to_move
            return

        if self.layout.pass_button.rect.collidepoint(pos):
            if self.game.to_move not in self.engines:
                self.game.pass_move()
                self._enter_scoring_phase_if_needed()
            return

        if self.game.to_move in self.engines:
            return  # it's the bot's turn; ignore board clicks

        point = point_at_pixel(pos, self.game.board.size, self.layout.cell_size, self.layout.margin)
        if point is None:
            return
        try:
            if self.game.is_legal(point):
                self.game.play(point)
                self._enter_scoring_phase_if_needed()
        except IllegalMoveError:
            pass

    # -- drawing -----------------------------------------------------------

    def draw(self) -> None:
        self.screen.fill(_BACKGROUND)
        self._draw_grid()
        self._draw_star_points()
        self._draw_stones()
        self._draw_last_move_marker()
        if self.scoring_phase:
            self._draw_dead_stone_marks()
        self._draw_panel()

    def _draw_grid(self) -> None:
        size = self.game.board.size
        cell = self.layout.cell_size
        margin = self.layout.margin
        span = self.layout.board_pixels
        for i in range(size):
            y = margin + i * cell
            pygame.draw.line(self.screen, _LINE_COLOR, (margin, y), (margin + span, y))
            x = margin + i * cell
            pygame.draw.line(self.screen, _LINE_COLOR, (x, margin), (x, margin + span))

            label = self.small_font.render(column_label(i), True, _TEXT_COLOR)
            self.screen.blit(label, (x - label.get_width() // 2, margin + span + 8))
            row_text = self.small_font.render(str(row_label(i, size)), True, _TEXT_COLOR)
            self.screen.blit(row_text, (margin - 28, y - row_text.get_height() // 2))

    def _draw_star_points(self) -> None:
        try:
            points = standard_handicap_points(self.game.board.size, 9)
        except ValueError:
            return
        for point in points:
            x, y = pixel_at_point(point, self.layout.cell_size, self.layout.margin)
            pygame.draw.circle(self.screen, _LINE_COLOR, (x, y), 4)

    def _draw_stones(self) -> None:
        radius = self.layout.cell_size // 2 - 2
        for point in self.game.board.all_points():
            color = self.game.board.get(point)
            if color == Color.EMPTY:
                continue
            x, y = pixel_at_point(point, self.layout.cell_size, self.layout.margin)
            fill = _BLACK_STONE if color == Color.BLACK else _WHITE_STONE
            pygame.draw.circle(self.screen, fill, (x, y), radius)
            pygame.draw.circle(self.screen, _STONE_OUTLINE, (x, y), radius, width=1)

    def _draw_last_move_marker(self) -> None:
        for move in reversed(self.game.history):
            if move.is_pass:
                continue
            x, y = pixel_at_point(move.point, self.layout.cell_size, self.layout.margin)
            pygame.draw.circle(self.screen, _LAST_MOVE_MARKER, (x, y), 5, width=2)
            return

    def _draw_dead_stone_marks(self) -> None:
        for point in self.dead_stones:
            x, y = pixel_at_point(point, self.layout.cell_size, self.layout.margin)
            offset = self.layout.cell_size // 2 - 4
            pygame.draw.line(self.screen, _DEAD_STONE_MARK, (x - offset, y - offset), (x + offset, y + offset), 2)
            pygame.draw.line(self.screen, _DEAD_STONE_MARK, (x - offset, y + offset), (x + offset, y - offset), 2)

    def _draw_panel(self) -> None:
        panel_rect = pygame.Rect(self.layout.panel_x, 0, self.layout.panel_width, self.layout.height)
        pygame.draw.rect(self.screen, _PANEL_BG, panel_rect)

        lines: List[str] = []
        if self.resigned_by is not None:
            winner = opponent(self.resigned_by)
            lines.append(f"{self.resigned_by.name.title()} resigns")
            lines.append(f"{winner.name.title()} wins")
        elif self.scoring_phase:
            result = compute_score_with_dead_stones(self.game, self.dead_stones)
            lines.append("Scoring: click stones")
            lines.append("to mark dead")
            lines.append("")
            lines.append(f"Black: {result.black:g}")
            lines.append(f"White: {result.white:g}")
            winner = result.winner
            lines.append(f"Winner: {winner.name.title() if winner else 'tie'}")
        else:
            lines.append(f"To move: {self.game.to_move.name.title()}")
            captured_by_black = sum(len(m.captured) for m in self.game.history if m.color == Color.BLACK)
            captured_by_white = sum(len(m.captured) for m in self.game.history if m.color == Color.WHITE)
            lines.append(f"Captured by Black: {captured_by_black}")
            lines.append(f"Captured by White: {captured_by_white}")
            lines.append("")
            live = self.game.score()
            lines.append("Live area score:")
            lines.append(f"Black: {live.black:g}")
            lines.append(f"White: {live.white:g}")

        y = 20
        for line in lines:
            if line:
                surf = self.font.render(line, True, _TEXT_COLOR)
                self.screen.blit(surf, (self.layout.panel_x + 20, y))
            y += 26

        if self.resigned_by is None:
            button = self.layout.done_button if self.scoring_phase else self.layout.pass_button
            self._draw_button(button)
            if not self.scoring_phase:
                self._draw_button(self.layout.resign_button)

    def _draw_button(self, button: _Button) -> None:
        pygame.draw.rect(self.screen, _BUTTON_BG, button.rect)
        pygame.draw.rect(self.screen, _BUTTON_BORDER, button.rect, width=2)
        label = self.font.render(button.label, True, _TEXT_COLOR)
        self.screen.blit(
            label,
            (
                button.rect.centerx - label.get_width() // 2,
                button.rect.centery - label.get_height() // 2,
            ),
        )

    # -- main loop -----------------------------------------------------

    def run(self) -> None:
        clock = pygame.time.Clock()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)

            self.maybe_play_bot_move()
            self.draw()
            pygame.display.flip()
            clock.tick(30)
        pygame.quit()
