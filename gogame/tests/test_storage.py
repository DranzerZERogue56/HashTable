from pathlib import Path

from gogame import storage
from gogame.board import Color
from gogame.bot import HeuristicBot
from gogame.rules import GameState, Rules
from gogame.session import GameSession, Phase


def _played_session(tmp_path):
    session = GameSession(
        GameState(Rules(board_size=9, komi=5.5)),
        engines={Color.WHITE: HeuristicBot(Color.WHITE, seed=2)},
    )
    for point in [(2, 2), (6, 6), (3, 3)]:
        session.tap_point(point)
        session.confirm()
        session.maybe_play_bot_move()
    return session


def test_has_save_is_false_before_anything_is_written(tmp_path):
    assert not storage.has_save(tmp_path)
    assert storage.load(tmp_path) is None


def test_round_trip_preserves_position_rules_and_bot_color(tmp_path):
    session = _played_session(tmp_path)
    storage.save(session, tmp_path)
    assert storage.has_save(tmp_path)

    restored = storage.load(tmp_path)
    assert restored is not None
    assert restored.game.board == session.game.board
    assert restored.game.rules.board_size == 9
    assert restored.game.rules.komi == 5.5
    assert restored.to_move == session.to_move
    assert len(restored.game.history) == len(session.game.history)
    assert set(restored.engines) == {Color.WHITE}


def test_round_trip_preserves_dead_stones_and_scoring_phase(tmp_path):
    session = GameSession(GameState(Rules(board_size=9)))
    session.tap_point((4, 4))
    session.confirm()
    session.tap_point((2, 2))
    session.confirm()
    session.pass_move()
    session.pass_move()
    assert session.phase == Phase.SCORING
    session.toggle_dead((4, 4))
    storage.save(session, tmp_path)

    restored = storage.load(tmp_path)
    assert restored is not None
    assert restored.phase == Phase.SCORING
    assert restored.dead_stones == {(4, 4)}
    assert restored.score().black == session.score().black


def test_round_trip_preserves_resignation(tmp_path):
    session = GameSession(GameState(Rules(board_size=9)))
    session.tap_point((4, 4))
    session.confirm()
    session.resign()
    storage.save(session, tmp_path)

    restored = storage.load(tmp_path)
    assert restored is not None
    assert restored.phase == Phase.RESIGNED
    assert restored.resigned_by == Color.WHITE
    assert restored.winner == Color.BLACK


def test_pending_preview_is_not_restored(tmp_path):
    session = GameSession(GameState(Rules(board_size=9)))
    session.tap_point((4, 4))
    assert session.phase == Phase.PENDING_CONFIRM
    storage.save(session, tmp_path)

    restored = storage.load(tmp_path)
    assert restored is not None
    assert restored.pending_point is None
    assert restored.phase == Phase.PLAYING
    assert restored.game.board.get((4, 4)) == Color.EMPTY


def test_handicap_game_round_trips(tmp_path):
    session = GameSession(GameState(Rules(board_size=19), handicap=4))
    storage.save(session, tmp_path)
    restored = storage.load(tmp_path)
    assert restored is not None
    assert restored.game.handicap == 4
    assert restored.game.board == session.game.board
    assert restored.to_move == Color.WHITE


def test_corrupt_save_returns_none_instead_of_raising(tmp_path):
    (tmp_path / storage.SAVE_NAME).write_text("this is not SGF at all", encoding="utf-8")
    assert storage.load(tmp_path) is None


def test_corrupt_sidecar_still_restores_the_game(tmp_path):
    session = _played_session(tmp_path)
    storage.save(session, tmp_path)
    (tmp_path / storage.META_NAME).write_text("{not json", encoding="utf-8")
    assert storage.load(tmp_path) is None


def test_clear_removes_the_save(tmp_path):
    session = _played_session(tmp_path)
    storage.save(session, tmp_path)
    storage.clear(tmp_path)
    assert not storage.has_save(tmp_path)
    storage.clear(tmp_path)  # idempotent


def test_state_dir_is_absolute_and_named_for_the_app(monkeypatch):
    monkeypatch.delenv("ANDROID_PRIVATE", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    path = storage.state_dir()
    assert path.is_absolute()
    assert path.name == "gogame"


def test_state_dir_prefers_android_private(monkeypatch):
    monkeypatch.setenv("ANDROID_PRIVATE", "/data/data/org.hashtable.gogame/files")
    assert storage.state_dir() == Path("/data/data/org.hashtable.gogame/files")
