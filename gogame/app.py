"""Kivy UI: the only framework-aware module in the package.

Everything that decides anything lives in layout.py (board geometry) and
session.py (phases, taps, bot turns); this module draws them and routes
touches back. board.py, rules.py, sgf.py and bot.py know nothing about
any of it. The pixels for the wood and the stones are arithmetic in
skin.py -- this module only wraps them in GPU textures and places them.

Coordinate note: layout.py works y-down from the top-left, while Kivy is
y-up from the bottom-left. BoardWidget._to_widget / _from_widget are the
only two places that conversion happens.

Nothing here draws an antialiased shape with a GL primitive. Anything
round or diagonal -- stones, star points, the confirm ring, the dead-stone
crosses -- is a texture from skin.py, and every straight line is a
Rectangle snapped to whole pixels. That combination is what stops the
board looking grainy on a high-density phone panel: GL gives an `Ellipse`
a stair-stepped edge, and a `Line` of width 1 is one *pixel* wide however
dense the screen, landing half on one pixel column and half on the next.
"""

from __future__ import annotations

import os

# Kivy parses sys.argv on import and rejects flags it doesn't know, which
# would break gogame/main.py's own CLI. Must be set before importing kivy.
os.environ.setdefault("KIVY_NO_ARGS", "1")

from typing import Callable, Dict, List, Optional, Tuple  # noqa: E402

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.text import Label as CoreLabel  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.graphics import Color as Paint  # noqa: E402
from kivy.graphics import Rectangle, RoundedRectangle  # noqa: E402
from kivy.graphics.texture import Texture  # noqa: E402
from kivy.metrics import Metrics, dp  # noqa: E402
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivy.uix.button import Button  # noqa: E402
from kivy.uix.label import Label  # noqa: E402
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager  # noqa: E402
from kivy.uix.spinner import Spinner  # noqa: E402
from kivy.uix.widget import Widget  # noqa: E402

from . import skin, storage
from .board import Color
from .bot import Engine, HeuristicBot
from .layout import column_label, compute_layout, pixel_at_point, point_at_pixel, row_label
from .rules import GameState, Rules, standard_handicap_points
from .session import GameSession, Phase

__all__ = ["GoApp", "BoardWidget", "PanelButton", "PanelSpinner", "build_session"]

BOARD_SIZES = [9, 13, 19]
KOMI_CHOICES = ["0.5", "5.5", "6.5", "7.5"]
BOT_TICK_SECONDS = 0.35

PANEL_PORTRAIT_DP = 150
PANEL_LANDSCAPE_DP = 210
BUTTON_HEIGHT_DP = 60  # comfortably above Android's 48dp touch minimum
CORNER_DP = 6
SLAB_INSET_DP = 6  # narrow strip of table showing around the board

# Texture resolutions. All powers of two: GLES2 will not mipmap a
# non-power-of-two texture, and without mipmaps a 128px stone scaled down
# to a 9x9 board's ~40px shimmers as it is resampled.
STONE_TEXELS = 128
SHADOW_TEXELS = 64
RING_TEXELS = 64
CROSS_TEXELS = 64
DOT_TEXELS = 32
SLAB_TEXELS = 256
TABLE_TEXELS = 128


def build_session(
    board_size: int = 9,
    komi: float = 7.5,
    handicap: int = 0,
    human_color: Optional[Color] = Color.BLACK,
) -> GameSession:
    """Start a game. `human_color` None means bot vs bot; to play both
    sides yourself, pass no engines by using human_color=Color.EMPTY."""
    game = GameState(Rules(board_size=board_size, komi=komi), handicap=handicap)
    engines: Dict[Color, Engine] = {}
    if human_color is None:
        engines[Color.BLACK] = HeuristicBot(Color.BLACK)
        engines[Color.WHITE] = HeuristicBot(Color.WHITE)
    elif human_color in (Color.BLACK, Color.WHITE):
        bot_color = Color.WHITE if human_color == Color.BLACK else Color.BLACK
        engines[bot_color] = HeuristicBot(bot_color)
    return GameSession(game, engines=engines)


# -- textures --------------------------------------------------------------
#
# Generated once on first use and kept for the process: they cost ~200 ms
# of Python arithmetic altogether and never change, since a stone is drawn
# by scaling one texture to whatever radius the layout asks for rather
# than by regenerating it per size.

# key -> (texture, reload callback kept alive deliberately)
_TEXTURES: Dict[str, Tuple[Texture, Callable]] = {}


def _rows_bottom_first(pixels: bytes, width: int, height: int) -> bytes:
    """Reverse the row order of an RGBA buffer.

    skin.py emits rows top-first; OpenGL reads the first row as the bottom.
    Reversing the bytes here rather than calling `Texture.flip_vertical()`
    keeps the fix in the data: flipping is a change to the texture object's
    coordinates, which a GL context loss can reset, and re-applying it on
    reload would flip an already-flipped texture back.
    """
    stride = width * 4
    return b"".join(
        pixels[y * stride:(y + 1) * stride] for y in range(height - 1, -1, -1)
    )


def _texture(key: str, factory: Callable[[], skin.Texels]) -> Texture:
    entry = _TEXTURES.get(key)
    if entry is None:
        pixels, width, height = factory()
        buffer = _rows_bottom_first(pixels, width, height)
        texture = Texture.create(size=(width, height), colorfmt="rgba", mipmap=True)

        def upload(target: Texture = None) -> None:
            # Also the reload path: Android can drop the GL context while
            # the app is backgrounded, and Kivy then recreates the texture
            # but has no idea what was in it. Without this the board comes
            # back from a phone call as blank white squares.
            target = target if target is not None else texture
            target.blit_buffer(buffer, colorfmt="rgba", bufferfmt="ubyte")
            target.min_filter = "linear_mipmap_linear"
            target.mag_filter = "linear"
            target.wrap = "clamp_to_edge"

        upload()
        texture.add_reload_observer(upload)
        # Kivy holds reload observers weakly, so the closure has to be kept
        # alive here or it is collected and the reload silently stops working.
        entry = (texture, upload)
        _TEXTURES[key] = entry
    return entry[0]


def _stone_texture(color: Color) -> Texture:
    """Slate takes a tight, bright highlight; clamshell a broad, soft one.

    That difference is most of what makes the two read as different
    materials rather than as one shape in two colours.
    """
    if color == Color.BLACK:
        return _texture(
            "stone-black",
            lambda: skin.stone_pixels(
                STONE_TEXELS, skin.BLACK_STONE,
                gloss=0.62, shininess=30.0, ambient=0.30, rim=0.20,
            ),
        )
    return _texture(
        "stone-white",
        lambda: skin.stone_pixels(
            STONE_TEXELS, skin.WHITE_STONE,
            gloss=0.38, shininess=13.0, ambient=0.54, rim=0.10,
        ),
    )


def _slab_texture() -> Texture:
    return _texture("slab", lambda: skin.wood_pixels(SLAB_TEXELS, SLAB_TEXELS))


def _table_texture() -> Texture:
    # Darker, coarser grain and almost no sheen: it has to stay behind the
    # board rather than compete with it.
    return _texture(
        "table",
        lambda: skin.wood_pixels(
            TABLE_TEXELS, TABLE_TEXELS, skin.TABLE_WOOD,
            seed=19, grain=0.10, speckle=0.03, vignette=0.05, sheen=0.04,
        ),
    )


def _shadow_texture() -> Texture:
    return _texture("shadow", lambda: skin.soft_shadow_pixels(SHADOW_TEXELS))


def _ring_texture() -> Texture:
    return _texture("ring", lambda: skin.ring_pixels(RING_TEXELS, skin.MARKER, 0.17))


def _cross_texture() -> Texture:
    return _texture("cross", lambda: skin.cross_pixels(CROSS_TEXELS, skin.MARKER, 0.15))


def _dot_texture(color: skin.RGB, key: str) -> Texture:
    return _texture(f"dot-{key}", lambda: skin.disc_pixels(DOT_TEXELS, color))


# CoreLabel allocates a texture per call, and the board redraws on every
# tap and every bot tick, so the coordinate labels are cached by the only
# things that change them.
_LABELS: Dict[Tuple[str, int], Texture] = {}


def _label_texture(text: str, font_size: int) -> Texture:
    key = (text, font_size)
    texture = _LABELS.get(key)
    if texture is None:
        label = CoreLabel(
            text=text, font_size=font_size, bold=True, color=(*skin.GRID_LINE, 1)
        )
        label.refresh()
        texture = label.texture
        _LABELS[key] = texture
    return texture


class BoardWidget(Widget):
    """Draws the board and turns touches into session taps."""

    def __init__(self, session: GameSession, on_change: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(**kwargs)
        self.session = session
        self.on_change = on_change
        self.bind(pos=self.redraw, size=self.redraw)

    @property
    def layout(self):
        # Computed on the slab, not the widget. The coordinate labels sit
        # in the board's margin, and in landscape that margin lands exactly
        # on the widget edge -- so measuring the full widget put the column
        # letters on the table below the wood.
        inset = 2 * dp(SLAB_INSET_DP)
        return compute_layout(
            self.session.game.board.size,
            max(1, int(self.width - inset)),
            max(1, int(self.height - inset)),
            Metrics.density,
        )

    # -- coordinate conversion (the only y-flip in the codebase) --------
    #
    # Also the only place the slab inset is applied, so drawing and touches
    # cannot disagree about where the board starts.

    def _to_widget(self, lx: float, ly: float) -> Tuple[float, float]:
        inset = dp(SLAB_INSET_DP)
        return self.x + inset + lx, self.top - inset - ly

    def _from_widget(self, wx: float, wy: float) -> Tuple[float, float]:
        inset = dp(SLAB_INSET_DP)
        return wx - self.x - inset, self.top - inset - wy

    # -- input -----------------------------------------------------------

    def on_touch_down(self, touch) -> bool:
        if not self.collide_point(*touch.pos):
            return False
        lx, ly = self._from_widget(*touch.pos)
        point = point_at_pixel(lx, ly, self.layout)
        if point is not None and self.session.tap_point(point):
            self.redraw()
            if self.on_change is not None:
                self.on_change()
        return True

    # -- drawing -----------------------------------------------------------

    def redraw(self, *_args) -> None:
        self.canvas.clear()
        session = self.session
        lay = self.layout
        size = session.game.board.size
        density = max(1.0, Metrics.density)

        # Kivy's `with canvas` pushes a thread-local context, so the
        # instructions created by these helpers land on this canvas.
        with self.canvas:
            self._draw_table()
            self._draw_slab(lay)
            self._draw_grid(lay, size, density)
            self._draw_star_points(lay, size)
            self._draw_coordinate_labels(lay, size)
            self._draw_stones(session.game.board, lay)
            self._draw_annotations(session, lay)

    def _draw_table(self) -> None:
        """Dark wood under everything.

        The board is square and the screen is not, so there is always space
        around it. Filling that with a table rather than more board colour
        is what makes the slab read as an object sitting on something.
        """
        Paint(1, 1, 1, 1)
        Rectangle(texture=_table_texture(), pos=self.pos, size=self.size)

    def _draw_slab(self, lay) -> None:
        """The wooden board, filling its area but for a thin inset.

        Deliberately *not* `lay.board_box`, which is the square the grid
        needs. A square slab on a 9:18 phone leaves a third of the screen
        as bare table above and below the board, which reads as wasted
        space rather than as a table. Filling the area instead and letting
        the table show as a narrow frame keeps the slab looking like a
        solid object -- rounded corners, drop shadow -- with nothing idle
        around it. The grid stays centred inside it, so the extra height
        becomes board margin.
        """
        inset = dp(SLAB_INSET_DP)
        x, y = self.x + inset, self.y + inset
        width, height = self.width - 2 * inset, self.height - 2 * inset
        if width <= 0 or height <= 0:
            return
        radius = dp(CORNER_DP)

        # Soft drop shadow: concentric rounded rectangles whose alpha
        # accumulates toward the middle. Cheaper than a blurred texture and
        # indistinguishable once it is this diffuse.
        drop = dp(2)
        for step in range(3, 0, -1):
            grow = step * dp(2)
            Paint(0, 0, 0, 0.12)
            RoundedRectangle(
                pos=(x - grow, y - grow - drop),
                size=(width + 2 * grow, height + 2 * grow),
                radius=[radius + grow],
            )

        Paint(1, 1, 1, 1)
        RoundedRectangle(
            texture=_slab_texture(),
            pos=(x, y),
            size=(width, height),
            radius=[radius],
        )

    def _draw_grid(self, lay, size: int, density: float) -> None:
        """Ruled lines, as whole-pixel rectangles.

        Widths scale with density so the grid keeps the same physical
        weight on a phone as on a desktop, and the two outer lines are
        heavier, which is how a real board is ruled.
        """
        thin = max(1, int(round(density * 0.9)))
        thick = max(thin + 1, int(round(density * 1.7)))
        Paint(*skin.GRID_LINE, 1)
        for i in range(size):
            offset = i * lay.cell
            weight = thick if i in (0, size - 1) else thin

            left, row_y = self._to_widget(lay.origin_x, lay.origin_y + offset)
            self._bar(left, row_y - weight / 2.0, lay.span, weight)

            col_x, top = self._to_widget(lay.origin_x + offset, lay.origin_y)
            self._bar(col_x - weight / 2.0, top - lay.span, weight, lay.span)

    @staticmethod
    def _bar(x: float, y: float, width: float, height: float) -> None:
        """A rectangle snapped to the pixel grid, so it cannot come out
        blurred or half-toned the way a sub-pixel line does."""
        Rectangle(
            pos=(round(x), round(y)),
            size=(max(1, round(width)), max(1, round(height))),
        )

    def _draw_star_points(self, lay, size: int) -> None:
        radius = max(dp(2.0), lay.cell / 9.0)
        texture = _dot_texture(skin.GRID_LINE, "line")
        Paint(1, 1, 1, 1)
        for point in self._star_points(size):
            x, y = self._to_widget(*pixel_at_point(point, lay))
            Rectangle(
                texture=texture,
                pos=(x - radius, y - radius),
                size=(radius * 2, radius * 2),
            )

    def _draw_stones(self, board, lay) -> None:
        radius = lay.stone_radius
        shadow = _shadow_texture()
        # Wider than the stone and nudged away from skin.py's light, so the
        # stones sit on the wood instead of in it.
        halo = radius * 1.32
        offset = radius * 0.13
        for point in board.all_points():
            stone = board.get(point)
            if stone == Color.EMPTY:
                continue
            x, y = self._to_widget(*pixel_at_point(point, lay))
            Paint(1, 1, 1, 1)
            Rectangle(
                texture=shadow,
                pos=(x - halo + offset, y - halo - offset),
                size=(halo * 2, halo * 2),
            )
            Rectangle(
                texture=_stone_texture(stone),
                pos=(x - radius, y - radius),
                size=(radius * 2, radius * 2),
            )

    def _draw_annotations(self, session, lay) -> None:
        radius = lay.stone_radius

        pending = session.pending_point
        if pending is not None:
            x, y = self._to_widget(*pixel_at_point(pending, lay))
            # Barely translucent. A tap has to show clearly *which colour*
            # is about to be played, and blending a near-black stone into
            # honey wood at any lower alpha turns it into an indeterminate
            # brown smudge that reads as neither colour. The ring is what
            # says "not placed yet"; the stone only has to say "black".
            Paint(1, 1, 1, 0.88)
            Rectangle(
                texture=_stone_texture(session.to_move),
                pos=(x - radius, y - radius),
                size=(radius * 2, radius * 2),
            )
            ring = radius * 1.14
            Paint(1, 1, 1, 1)
            Rectangle(
                texture=_ring_texture(),
                pos=(x - ring, y - ring),
                size=(ring * 2, ring * 2),
            )

        last = session.last_move_point
        if last is not None and last != pending:
            # A filled dot, so it can't be confused with the ring that
            # marks the stone still awaiting confirmation.
            dot = max(dp(2.0), radius / 3.0)
            x, y = self._to_widget(*pixel_at_point(last, lay))
            Paint(1, 1, 1, 1)
            Rectangle(
                texture=_dot_texture(skin.MARKER, "marker"),
                pos=(x - dot, y - dot),
                size=(dot * 2, dot * 2),
            )

        if session.phase in (Phase.SCORING, Phase.FINISHED):
            cross = _cross_texture()
            arm = radius * 0.98
            Paint(1, 1, 1, 1)
            for point in session.dead_stones:
                x, y = self._to_widget(*pixel_at_point(point, lay))
                Rectangle(
                    texture=cross,
                    pos=(x - arm, y - arm),
                    size=(arm * 2, arm * 2),
                )

    def _star_points(self, size: int) -> List:
        try:
            return standard_handicap_points(size, 9)
        except ValueError:
            return []

    def _draw_coordinate_labels(self, lay, size: int) -> None:
        font_size = lay.label_font_size
        # 0.6 of the margin, not half: at half, the corner labels (row "1"
        # and column "A") crowd each other and the outer grid line.
        gap = int(lay.margin * 0.6)
        for i in range(size):
            x, _y = self._to_widget(lay.origin_x + i * lay.cell, 0)
            _bx, baseline = self._to_widget(0, lay.origin_y + lay.span + gap)
            self._blit_centred(column_label(i), x, baseline, font_size)

            _x2, y2 = self._to_widget(0, lay.origin_y + i * lay.cell)
            left, _ = self._to_widget(lay.origin_x - gap, 0)
            self._blit_centred(str(row_label(i, size)), left, y2, font_size)

    def _blit_centred(self, text: str, cx: float, cy: float, font_size: int) -> None:
        texture = _label_texture(text, font_size)
        Paint(1, 1, 1, 1)
        # Whole pixels: a glyph texture drawn on a half pixel is resampled
        # and comes out soft, which at this size looks like a bad font.
        Rectangle(
            texture=texture,
            pos=(round(cx - texture.width / 2), round(cy - texture.height / 2)),
            size=texture.size,
        )


class _Lacquered:
    """Rounded, flat background for Button and its subclasses.

    Kivy's default button is a grey gradient image that looks like a
    toolkit widget dropped on a wooden board. Suppressing all four
    background images and drawing a rounded rectangle instead keeps the
    press and disabled states, which is the part worth keeping.

    A mixin because Spinner subclasses Button, and a spinner with square
    corners sitting beside rounded buttons reads as unfinished.
    """

    def __init__(self, **kwargs):
        for slot in (
            "background_normal",
            "background_down",
            "background_disabled_normal",
            "background_disabled_down",
        ):
            kwargs.setdefault(slot, "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        kwargs.setdefault("color", (*skin.BUTTON_TEXT, 1))
        super().__init__(**kwargs)
        with self.canvas.before:
            self._paint = Paint(*skin.BUTTON_BG, 1)
            self._bg = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[dp(CORNER_DP)]
            )
        self.bind(pos=self._restyle, size=self._restyle, state=self._restyle,
                  disabled=self._restyle)

    def _restyle(self, *_args) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size
        if self.disabled:
            self._paint.rgba = (*skin.BUTTON_BG, 0.4)
            self.color = (*skin.TEXT_MUTED, 0.5)
        elif self.state == "down":
            self._paint.rgba = (*skin.PANEL_EDGE, 1)
            self.color = (*skin.BUTTON_TEXT, 1)
        else:
            self._paint.rgba = (*skin.BUTTON_BG, 1)
            self.color = (*skin.BUTTON_TEXT, 1)


class PanelButton(_Lacquered, Button):
    pass


class PanelSpinner(_Lacquered, Spinner):
    pass


def _fill(widget, color: skin.RGB, alpha: float = 1.0):
    """Paint a flat background behind `widget` and keep it in step."""
    with widget.canvas.before:
        Paint(*color, alpha)
        rect = Rectangle(pos=widget.pos, size=widget.size)

    def sync(*_args) -> None:
        rect.pos = widget.pos
        rect.size = widget.size

    widget.bind(pos=sync, size=sync)
    return rect


def _wood_fill(widget):
    """Table wood behind `widget`, for the screens that are not the board."""
    with widget.canvas.before:
        Paint(1, 1, 1, 1)
        rect = Rectangle(texture=_table_texture(), pos=widget.pos, size=widget.size)

    def sync(*_args) -> None:
        rect.pos = widget.pos
        rect.size = widget.size

    widget.bind(pos=sync, size=sync)
    return rect


class BoardScreen(Screen):
    def __init__(self, app: "GoApp", **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.box = BoxLayout()
        self.board = BoardWidget(app.session, on_change=self.refresh)

        self.panel = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        _fill(self.panel, skin.PANEL_BG)

        self.status = Label(
            color=(*skin.TEXT, 1), bold=True, font_size=dp(17),
            size_hint_y=None, height=dp(28),
        )
        self.detail = Label(
            color=(*skin.TEXT_MUTED, 1), font_size=dp(14),
            halign="center", valign="middle",
        )
        self.detail.bind(size=lambda w, _v: setattr(w, "text_size", w.size))
        self.buttons = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(BUTTON_HEIGHT_DP))

        self.panel.add_widget(self.status)
        self.panel.add_widget(self.detail)
        self.panel.add_widget(self.buttons)
        self.box.add_widget(self.board)
        self.box.add_widget(self.panel)
        self.add_widget(self.box)

        Window.bind(size=self._apply_orientation)
        self._apply_orientation()

    def _apply_orientation(self, *_args) -> None:
        """Compact panel pinned to one edge; the board takes the rest and
        sits centred on its own wood, which reads as a board on a table
        rather than as empty space."""
        portrait = Window.height >= Window.width
        self.box.orientation = "vertical" if portrait else "horizontal"
        self.board.size_hint = (1, 1)
        if portrait:
            self.panel.size_hint = (1, None)
            self.panel.height = dp(PANEL_PORTRAIT_DP)
        else:
            self.panel.size_hint = (None, 1)
            self.panel.width = dp(PANEL_LANDSCAPE_DP)

    # -- refresh ---------------------------------------------------------

    def attach(self, session: GameSession) -> None:
        self.board.session = session
        self.refresh()

    def refresh(self, *_args) -> None:
        session = self.app.session
        self.status.text = session.status_text()
        self.detail.text = self._detail_text(session)
        self._rebuild_buttons(session)
        self.board.redraw()
        self.app.persist()

    def _detail_text(self, session: GameSession) -> str:
        score = session.score()
        captures = (
            f"Captures  B {session.captures_by(Color.BLACK)}"
            f"   W {session.captures_by(Color.WHITE)}"
        )
        heading = "Final score" if session.phase in (Phase.SCORING, Phase.FINISHED) else "Area score"
        return f"{captures}\n{heading}  B {score.black:g}   W {score.white:g}"

    def _rebuild_buttons(self, session: GameSession) -> None:
        self.buttons.clear_widgets()
        for label, callback, enabled in self._button_spec(session):
            button = PanelButton(text=label, font_size=dp(15))
            button.disabled = not enabled
            button.bind(on_release=lambda _b, cb=callback: cb())
            self.buttons.add_widget(button)

    def _button_spec(self, session: GameSession) -> List[Tuple[str, Callable[[], None], bool]]:
        if session.phase == Phase.PENDING_CONFIRM:
            return [
                ("Place", self._do(session.confirm), True),
                ("Cancel", self._do(session.cancel), True),
            ]
        if session.phase == Phase.SCORING:
            return [
                ("Done", self._do(session.finish_scoring), True),
                ("New game", self.app.show_new_game, True),
            ]
        if session.phase == Phase.FINISHED:
            return [
                ("Mark dead", self._do(session.resume_scoring), True),
                ("New game", self.app.show_new_game, True),
            ]
        if session.phase == Phase.RESIGNED:
            return [("New game", self.app.show_new_game, True)]
        return [
            ("Pass", self._do(session.pass_move), session.is_human_turn()),
            ("Resign", self._do(session.resign), True),
            ("New game", self.app.show_new_game, True),
        ]

    def _do(self, action: Callable[[], bool]) -> Callable[[], None]:
        def run() -> None:
            if action():
                self.refresh()

        return run

    def handle_back(self) -> bool:
        """True if the back press was consumed."""
        session = self.app.session
        if session.pending_point is not None:
            session.cancel()
            self.refresh()
            return True
        return False


class NewGameScreen(Screen):
    def __init__(self, app: "GoApp", **kwargs):
        super().__init__(**kwargs)
        self.app = app
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(10))
        _wood_fill(root)

        root.add_widget(
            Label(
                text="New game", color=(*skin.TEXT, 1), bold=True, font_size=dp(24),
                size_hint_y=None, height=dp(46),
            )
        )
        # Flexible spacers above and below the rows, so the form sits in
        # the middle of the screen rather than crowding the title with a
        # tall empty gap underneath it.
        root.add_widget(Widget())

        self.size_spinner = self._row(root, "Board", [str(s) for s in BOARD_SIZES], "9")
        self.komi_spinner = self._row(root, "Komi", KOMI_CHOICES, "7.5")
        self.handicap_spinner = self._row(root, "Handicap", ["0"] + [str(n) for n in range(2, 10)], "0")
        self.color_spinner = self._row(
            root, "You play", ["Black", "White", "Both (hotseat)", "Watch bots"], "Black"
        )

        start = PanelButton(text="Start", size_hint_y=None, height=dp(58), font_size=dp(19), bold=True)
        start.bind(on_release=lambda *_: self.app.start_new_game(*self.selection()))
        root.add_widget(Widget())
        root.add_widget(start)
        self.add_widget(root)

    def _row(self, parent, caption: str, values: List[str], default: str) -> Spinner:
        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(10))
        label = Label(
            text=caption, color=(*skin.TEXT, 1), font_size=dp(16),
            size_hint_x=0.45, halign="left", valign="middle",
        )
        label.bind(size=lambda w, _v: setattr(w, "text_size", w.size))
        row.add_widget(label)
        spinner = PanelSpinner(text=default, values=values, font_size=dp(16))
        row.add_widget(spinner)
        parent.add_widget(row)
        return spinner

    def selection(self) -> Tuple[int, float, int, Optional[Color]]:
        human = {
            "Black": Color.BLACK,
            "White": Color.WHITE,
            "Both (hotseat)": Color.EMPTY,
            "Watch bots": None,
        }[self.color_spinner.text]
        return (
            int(self.size_spinner.text),
            float(self.komi_spinner.text),
            int(self.handicap_spinner.text),
            human,
        )


class GoApp(App):
    title = "Go"

    def __init__(self, session: Optional[GameSession] = None, autosave: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.autosave = autosave
        self.session = session or self._restore_or_new()
        self._tick_event = None

    def _restore_or_new(self) -> GameSession:
        if self.autosave:
            restored = storage.load()
            if restored is not None:
                return restored
        return build_session()

    def build(self):
        self.manager = ScreenManager(transition=NoTransition())
        self.board_screen = BoardScreen(self, name="board")
        self.new_game_screen = NewGameScreen(self, name="new")
        self.manager.add_widget(self.board_screen)
        self.manager.add_widget(self.new_game_screen)
        self.board_screen.refresh()
        Window.bind(on_keyboard=self._on_keyboard)
        self._tick_event = Clock.schedule_interval(self._tick, BOT_TICK_SECONDS)
        return self.manager

    # -- flow ------------------------------------------------------------

    def show_new_game(self) -> None:
        self.manager.current = "new"

    def start_new_game(
        self, board_size: int, komi: float, handicap: int, human_color: Optional[Color]
    ) -> None:
        self.session = build_session(board_size, komi, handicap, human_color)
        self.board_screen.attach(self.session)
        self.manager.current = "board"

    def _tick(self, _dt) -> None:
        if self.manager.current != "board":
            return
        if self.session.maybe_play_bot_move():
            self.board_screen.refresh()

    def persist(self) -> None:
        if not self.autosave:
            return
        try:
            storage.save(self.session)
        except OSError:
            pass  # a failed autosave must never interrupt play

    # -- platform hooks ----------------------------------------------------

    def _on_keyboard(self, _window, key, *_args) -> bool:
        if key != 27:  # ESC, and Android's BACK button
            return False
        if self.manager.current == "new":
            self.manager.current = "board"
            return True
        return self.board_screen.handle_back()

    def on_pause(self) -> bool:
        self.persist()
        return True  # False would let Android kill and restart the app

    def on_resume(self) -> None:
        self.board_screen.refresh()

    def on_stop(self) -> None:
        self.persist()
