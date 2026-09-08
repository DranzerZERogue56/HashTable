"""Autosave and restore, so an Android app kill doesn't lose the game.

The move record is written as SGF using the existing sgf.py, which keeps
the save file a legitimate game record you can open elsewhere. The few
things SGF has no room for -- which colors the bot is playing, which
stones are marked dead, and the interaction phase -- go in a small JSON
sidecar next to it.

A corrupt or unreadable save must never stop the app from starting, so
load() returns None instead of raising.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .board import Color, Point
from .bot import Engine, HeuristicBot
from .rules import IllegalMoveError
from .session import GameSession, Phase
from .sgf import SGFParseError, game_to_sgf, sgf_to_game

__all__ = ["state_dir", "save", "load", "clear", "has_save", "SAVE_NAME", "META_NAME"]

SAVE_NAME = "autosave.sgf"
META_NAME = "autosave.json"


def state_dir() -> Path:
    """Where to keep the autosave: app-private storage on Android, the
    usual XDG data directory elsewhere."""
    try:
        from android.storage import app_storage_path  # type: ignore

        return Path(app_storage_path())
    except ImportError:
        pass
    private = os.environ.get("ANDROID_PRIVATE")
    if private:
        return Path(private)
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "gogame"


def _paths(directory: Optional[Path]) -> tuple:
    base = Path(directory) if directory is not None else state_dir()
    return base, base / SAVE_NAME, base / META_NAME


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def has_save(directory: Optional[Path] = None) -> bool:
    _base, sgf_path, _meta_path = _paths(directory)
    return sgf_path.is_file()


def save(session: GameSession, directory: Optional[Path] = None) -> None:
    base, sgf_path, meta_path = _paths(directory)
    base.mkdir(parents=True, exist_ok=True)
    meta = {
        "version": 1,
        "bot_colors": sorted(int(c) for c in session.engines),
        "dead_stones": sorted([list(p) for p in session.dead_stones]),
        "phase": session.phase.value,
        "resigned_by": int(session.resigned_by) if session.resigned_by is not None else None,
    }
    _write_atomic(sgf_path, game_to_sgf(session.game))
    _write_atomic(meta_path, json.dumps(meta))


def clear(directory: Optional[Path] = None) -> None:
    _base, sgf_path, meta_path = _paths(directory)
    for path in (sgf_path, meta_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def load(
    directory: Optional[Path] = None,
    engine_factory: Optional[Callable[[Color], Engine]] = None,
) -> Optional[GameSession]:
    """Restore the autosaved session, or None if there isn't a usable one."""
    _base, sgf_path, meta_path = _paths(directory)
    make_engine = engine_factory or (lambda color: HeuristicBot(color))
    try:
        game = sgf_to_game(sgf_path.read_text(encoding="utf-8"))
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    except (OSError, ValueError, KeyError, SGFParseError, IllegalMoveError):
        return None

    engines: Dict[Color, Engine] = {}
    for raw in meta.get("bot_colors", []):
        try:
            color = Color(raw)
        except ValueError:
            continue
        if color != Color.EMPTY:
            engines[color] = make_engine(color)

    session = GameSession(game, engines=engines)

    dead: List[Point] = []
    for entry in meta.get("dead_stones", []):
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            dead.append((int(entry[0]), int(entry[1])))
    session.dead_stones = {p for p in dead if session.game.board.is_on_board(p)}

    resigned = meta.get("resigned_by")
    if resigned is not None:
        try:
            session.resigned_by = Color(resigned)
        except ValueError:
            session.resigned_by = None

    try:
        phase = Phase(meta.get("phase", session.phase.value))
    except ValueError:
        phase = session.phase
    # A pending preview is deliberately not restored -- an uncommitted
    # stone shouldn't survive the app being killed.
    if phase == Phase.PENDING_CONFIRM:
        phase = Phase.PLAYING
    if phase == Phase.RESIGNED and session.resigned_by is None:
        phase = Phase.PLAYING
    session.phase = phase

    return session
