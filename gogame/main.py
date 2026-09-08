"""CLI entry point: `python -m gogame.main [options]`."""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional

from .bot import Engine, HeuristicBot
from .board import Color
from .rules import GameState, Rules
from .sgf import sgf_to_game
from .ui import GoUI

_BOT_COLOR_CHOICES = ["black", "white", "both", "none"]


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play Go (weiqi) against a heuristic bot.")
    parser.add_argument("--size", type=int, default=19, help="board size (default: 19)")
    parser.add_argument("--komi", type=float, default=7.5, help="komi awarded to White (default: 7.5)")
    parser.add_argument(
        "--handicap", type=int, default=0, help="number of Black handicap stones, 0 or 2-9 (default: 0)"
    )
    parser.add_argument(
        "--bot-color",
        choices=_BOT_COLOR_CHOICES,
        default="white",
        help="which color(s) the heuristic bot plays (default: white)",
    )
    parser.add_argument(
        "--sgf", type=str, default=None, help="load a game from this SGF file instead of starting a new one"
    )
    return parser.parse_args(argv)


def _build_engines(bot_color: str) -> Dict[Color, Engine]:
    engines: Dict[Color, Engine] = {}
    if bot_color in ("black", "both"):
        engines[Color.BLACK] = HeuristicBot(Color.BLACK, seed=0xB1AC7)
    if bot_color in ("white", "both"):
        engines[Color.WHITE] = HeuristicBot(Color.WHITE, seed=0x71173)
    return engines


def build_game(args: argparse.Namespace) -> GameState:
    if args.sgf:
        with open(args.sgf, "r", encoding="utf-8") as handle:
            return sgf_to_game(handle.read())
    return GameState(Rules(board_size=args.size, komi=args.komi), handicap=args.handicap)


def main(argv: Optional[List[str]] = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    game = build_game(args)
    engines = _build_engines(args.bot_color)
    ui = GoUI(game, engines)
    ui.run()


if __name__ == "__main__":
    main()
