"""Kivy UI: the only framework-aware module in the package.

Everything that decides anything lives in layout.py (board geometry) and
session.py (phases, taps, bot turns); this module draws them and routes
touches back. board.py, rules.py, sgf.py and bot.py know nothing about
any of it.

Coordinate note: layout.py works y-down from the top-left, while Kivy is
y-up from the bottom-left. BoardWidget._to_widget / _from_widget are the
only two places that conversion happens.
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
from kivy.graphics import Ellipse, Line, Rectangle  # noqa: E402
from kivy.metrics import Metrics, dp  # noqa: E402
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivy.uix.button import Button  # noqa: E402
from kivy.uix.label import Label  # noqa: E402
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager  # noqa: E402
from kivy.uix.spinner import Spinner  # noqa: E402
from kivy.uix.widget import Widget  # noqa: E402

from . import storage
from .board import Color
from .bot import Engine, HeuristicBot
from .layout import column_label, compute_layout, pixel_at_point, point_at_pixel, row_label
from .rules import GameState, Rules, standard_handicap_points
from .session import GameSession, Phase

__all__ = ["GoApp", "BoardWidget", "build_session"]

BOARD_BG = (0.86, 0.70, 0.36, 1)
LINE = (0.16, 0.12, 0.04, 1)
BLACK_STONE = (0.08, 0.08, 0.08, 1)
WHITE_STONE = (0.96, 0.96, 0.96, 1)
STONE_EDGE = (0.16, 0.12, 0.04, 1)
MARKER = (0.80, 0.12, 0.12, 1)
PANEL_BG = (0.96, 0.94, 0.88, 1)
TEXT = (0.08, 0.08, 0.08, 1)

BOARD_SIZES = [9, 13, 19]
KOMI_CHOICES = ["0.5", "5.5", "6.5", "7.5"]
BOT_TICK_SECONDS = 0.35

PANEL_PORTRAIT_DP = 150
PANEL_LANDSCAPE_DP = 210
BUTTON_HEIGHT_DP = 60  # comfortably above Android's 48dp touch minimum


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


class BoardWidget(Widget):
    """Draws the board and turns touches into session taps."""

    def __init__(self, session: GameSession, on_change: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(**kwargs)
        self.session = session
        self.on_change = on_change
        self.bind(pos=self.redraw, size=self.redraw)

    @property
    def layout(self):
        return compute_layout(
            self.session.game.board.size,
            max(1, int(self.width)),
            max(1, int(self.height)),
            Metrics.density,
        )

    # -- coordinate conversion (the only y-flip in the codebase) --------

    def _to_widget(self, lx: float, ly: float) -> Tuple[float, float]:
        return self.x + lx, self.top - ly

    def _from_widget(self, wx: float, wy: float) -> Tuple[float, float]:
        return wx - self.x, self.top - wy

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
        board = session.game.board
        lay = self.layout
        size = board.size

        with self.canvas:
            # Fill the whole widget, not just the board: on a tall phone the
            # square board leaves space above and below, and bare black
            # bands there look like a rendering fault.
            Paint(*BOARD_BG)
            Rectangle(pos=self.pos, size=self.size)

            Paint(*LINE)
            for i in range(size):
                offset = i * lay.cell
                Line(
                    points=[
                        *self._to_widget(lay.origin_x, lay.origin_y + offset),
                        *self._to_widget(lay.origin_x + lay.span, lay.origin_y + offset),
                    ],
                    width=1,
                )
                Line(
                    points=[
                        *self._to_widget(lay.origin_x + offset, lay.origin_y),
                        *self._to_widget(lay.origin_x + offset, lay.origin_y + lay.span),
                    ],
                    width=1,
                )

            star_radius = max(2, lay.cell // 10)
            for point in self._star_points(size):
                x, y = self._to_widget(*pixel_at_point(point, lay))
                Ellipse(pos=(x - star_radius, y - star_radius), size=(star_radius * 2,) * 2)

            radius = lay.stone_radius
            for point in board.all_points():
                stone = board.get(point)
                if stone == Color.EMPTY:
                    continue
                x, y = self._to_widget(*pixel_at_point(point, lay))
                Paint(*(BLACK_STONE if stone == Color.BLACK else WHITE_STONE))
                Ellipse(pos=(x - radius, y - radius), size=(radius * 2,) * 2)
                Paint(*STONE_EDGE)
                Line(circle=(x, y, radius), width=1)

            pending = session.pending_point
            if pending is not None:
                ghost = BLACK_STONE if session.to_move == Color.BLACK else WHITE_STONE
                x, y = self._to_widget(*pixel_at_point(pending, lay))
                Paint(ghost[0], ghost[1], ghost[2], 0.55)
                Ellipse(pos=(x - radius, y - radius), size=(radius * 2,) * 2)
                Paint(*MARKER)
                Line(circle=(x, y, radius), width=2)

            last = session.last_move_point
            if last is not None and last != pending:
                # A filled dot, so it can't be confused with the ring that
                # marks the stone still awaiting confirmation.
                dot = max(2, radius // 3)
                x, y = self._to_widget(*pixel_at_point(last, lay))
                Paint(*MARKER)
                Ellipse(pos=(x - dot, y - dot), size=(dot * 2,) * 2)

            if session.phase in (Phase.SCORING, Phase.FINISHED):
                Paint(*MARKER)
                arm = max(3, radius - 2)
                for point in session.dead_stones:
                    x, y = self._to_widget(*pixel_at_point(point, lay))
                    Line(points=[x - arm, y - arm, x + arm, y + arm], width=2)
                    Line(points=[x - arm, y + arm, x + arm, y - arm], width=2)

            self._draw_coordinate_labels(lay, size)

    def _star_points(self, size: int) -> List:
        try:
            return standard_handicap_points(size, 9)
        except ValueError:
            return []

    def _draw_coordinate_labels(self, lay, size: int) -> None:
        font_size = lay.label_font_size
        gap = lay.margin // 2
        for i in range(size):
            x, _y = self._to_widget(lay.origin_x + i * lay.cell, 0)
            _bx, baseline = self._to_widget(0, lay.origin_y + lay.span + gap)
            self._blit_centred(column_label(i), x, baseline, font_size)

            _x2, y2 = self._to_widget(0, lay.origin_y + i * lay.cell)
            left, _ = self._to_widget(lay.origin_x - gap, 0)
            self._blit_centred(str(row_label(i, size)), left, y2, font_size)

    def _blit_centred(self, text: str, cx: float, cy: float, font_size: int) -> None:
        label = CoreLabel(text=text, font_size=font_size, color=TEXT)
        label.refresh()
        texture = label.texture
        Paint(1, 1, 1, 1)
        Rectangle(
            texture=texture,
            pos=(cx - texture.width / 2, cy - texture.height / 2),
            size=texture.size,
        )


class BoardScreen(Screen):
    def __init__(self, app: "GoApp", **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.box = BoxLayout()
        self.board = BoardWidget(app.session, on_change=self.refresh)

        self.panel = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(4))
        with self.panel.canvas.before:
            Paint(*PANEL_BG)
            self._panel_bg = Rectangle(pos=self.panel.pos, size=self.panel.size)
        self.panel.bind(pos=self._sync_panel_bg, size=self._sync_panel_bg)

        self.status = Label(color=TEXT, bold=True, size_hint_y=None, height=dp(26))
        self.detail = Label(color=TEXT, halign="center", valign="middle")
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

    def _sync_panel_bg(self, *_args) -> None:
        self._panel_bg.pos = self.panel.pos
        self._panel_bg.size = self.panel.size

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
            button = Button(text=label, font_size=dp(15))
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
        root = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(10))
        with root.canvas.before:
            Paint(*PANEL_BG)
            self._bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(
            pos=lambda *_: setattr(self._bg, "pos", root.pos),
            size=lambda *_: setattr(self._bg, "size", root.size),
        )

        root.add_widget(Label(text="New game", color=TEXT, bold=True, font_size=dp(22), size_hint_y=None, height=dp(40)))

        self.size_spinner = self._row(root, "Board", [str(s) for s in BOARD_SIZES], "9")
        self.komi_spinner = self._row(root, "Komi", KOMI_CHOICES, "7.5")
        self.handicap_spinner = self._row(root, "Handicap", ["0"] + [str(n) for n in range(2, 10)], "0")
        self.color_spinner = self._row(
            root, "You play", ["Black", "White", "Both (hotseat)", "Watch bots"], "Black"
        )

        start = Button(text="Start", size_hint_y=None, height=dp(56), font_size=dp(18))
        start.bind(on_release=lambda *_: self.app.start_new_game(*self.selection()))
        root.add_widget(Widget())
        root.add_widget(start)
        self.add_widget(root)

    def _row(self, parent, caption: str, values: List[str], default: str) -> Spinner:
        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        row.add_widget(Label(text=caption, color=TEXT, size_hint_x=0.45, halign="left"))
        spinner = Spinner(text=default, values=values, font_size=dp(16))
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
