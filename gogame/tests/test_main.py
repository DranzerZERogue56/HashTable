import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from gogame.board import Color
from gogame.main import _build_engines, _parse_args, build_game
from gogame.rules import GameState, Rules
from gogame.sgf import game_to_sgf


def test_parse_args_defaults():
    args = _parse_args([])
    assert args.size == 19
    assert args.komi == 7.5
    assert args.handicap == 0
    assert args.bot_color == "white"
    assert args.sgf is None


def test_parse_args_overrides():
    args = _parse_args(
        ["--size", "9", "--komi", "5.5", "--handicap", "4", "--bot-color", "both"]
    )
    assert args.size == 9
    assert args.komi == 5.5
    assert args.handicap == 4
    assert args.bot_color == "both"


def test_build_game_without_sgf_uses_cli_flags():
    args = _parse_args(["--size", "13", "--komi", "6.5", "--handicap", "2"])
    game = build_game(args)
    assert game.rules.board_size == 13
    assert game.rules.komi == 6.5
    assert game.handicap == 2
    assert game.to_move == Color.WHITE  # handicap >= 2 -> White plays first


def test_build_game_from_sgf_file(tmp_path):
    source = GameState(Rules(board_size=9, komi=5.5))
    source.play((2, 2))
    source.play((6, 6))
    sgf_path = tmp_path / "game.sgf"
    sgf_path.write_text(game_to_sgf(source))

    args = _parse_args(["--sgf", str(sgf_path)])
    game = build_game(args)
    assert game.rules.board_size == 9
    assert game.rules.komi == 5.5
    assert game.board == source.board
    assert len(game.history) == 2


def test_build_engines_for_each_bot_color_choice():
    assert _build_engines("none") == {}
    assert set(_build_engines("black").keys()) == {Color.BLACK}
    assert set(_build_engines("white").keys()) == {Color.WHITE}
    assert set(_build_engines("both").keys()) == {Color.BLACK, Color.WHITE}
