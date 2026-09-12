"""Pure geometry for the board display: no UI framework imports.

Coordinates are y-down with the origin at the top-left, matching the
(row, col) grid where row 0 is the top row. Kivy's origin is bottom-left
with y growing upward, so app.py flips y exactly once at the
drawing/touch boundary and nowhere else.

Sizes expressed in dp are multiplied by the display density, so touch
targets stay physically the same size on a high-DPI phone as on a
desktop (density 1.0).

Display labels follow the printed-board convention -- columns A-T
skipping I, rows numbered 1 at the bottom up to N at the top -- which is
unrelated to SGF's a-s letters in sgf.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Optional, Tuple

from .board import Point

__all__ = [
    "Rect",
    "Layout",
    "compute_layout",
    "point_at_pixel",
    "pixel_at_point",
    "column_label",
    "row_label",
]

_COLUMN_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"  # skips I, per Go convention

HIT_RADIUS_DP = 22.0  # keeps edge lines tappable when cells are small
PAD_DP = 8.0
MIN_CELL_PX = 8


def column_label(col: int) -> str:
    return _COLUMN_LETTERS[col]


def row_label(row: int, size: int) -> int:
    """Displayed row number: row 0 (top of the grid) is line `size`."""
    return size - row


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x < self.right and self.y <= y < self.bottom


@dataclass(frozen=True)
class Layout:
    board_size: int
    width: int  # the drawing area handed to the board
    height: int
    density: float
    cell: int
    margin: int
    origin_x: int  # pixel of intersection (row 0, col 0)
    origin_y: int
    span: int  # (board_size - 1) * cell
    hit_radius: int
    board_box: Rect

    @property
    def stone_radius(self) -> int:
        return max(2, self.cell // 2 - max(1, self.cell // 16))

    @property
    def label_font_size(self) -> int:
        # Floor scales with density: 9 raw pixels is legible on a desktop
        # and a smear on a 3x phone panel.
        return max(int(8 * self.density), int(self.cell * 0.38))


def compute_layout(
    board_size: int, width: int, height: int, density: float = 1.0
) -> Layout:
    """Centre the largest square board that fits in `width` x `height`.

    The surrounding panel is laid out by the UI framework; this only
    concerns the board itself.
    """
    pad = max(4, int(PAD_DP * density))
    available = min(width, height)
    # The +0.5 leaves roughly three quarters of a cell of margin on each
    # side for the coordinate labels.
    cell = max(MIN_CELL_PX, int(available / (board_size + 0.5)))
    span = (board_size - 1) * cell
    margin = max(pad, (available - span) // 2)
    box_side = span + 2 * margin

    box_x = (width - box_side) // 2
    box_y = (height - box_side) // 2
    board_box = Rect(box_x, box_y, box_side, box_side)

    return Layout(
        board_size=board_size,
        width=width,
        height=height,
        density=density,
        cell=cell,
        margin=margin,
        origin_x=box_x + margin,
        origin_y=box_y + margin,
        span=span,
        hit_radius=max(cell // 2, int(HIT_RADIUS_DP * density)),
        board_box=board_box,
    )


def pixel_at_point(point: Point, layout: Layout) -> Tuple[int, int]:
    row, col = point
    return layout.origin_x + col * layout.cell, layout.origin_y + row * layout.cell


def point_at_pixel(x: float, y: float, layout: Layout) -> Optional[Point]:
    """Nearest intersection to a tap, or None if the tap is too far away.

    The row/col are clamped before the distance check so a tap in the
    margin just outside the outermost line still reaches the edge
    intersections -- on a phone the first line is otherwise very hard to
    hit.
    """
    last = layout.board_size - 1
    col = min(last, max(0, round((x - layout.origin_x) / layout.cell)))
    row = min(last, max(0, round((y - layout.origin_y) / layout.cell)))
    center_x, center_y = pixel_at_point((row, col), layout)
    if hypot(x - center_x, y - center_y) > layout.hit_radius:
        return None
    return (row, col)
