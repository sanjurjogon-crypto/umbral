from __future__ import annotations

from umbral.models import Game


def _game(**overrides) -> Game:
    data = {
        "id": "test",
        "title": "Test",
        "system": "PC",
        "system_key": "pc",
    }
    data.update(overrides)
    return Game(**data)


def test_new_game_is_unplayed() -> None:
    assert _game().state == "unplayed"


def test_game_with_time_is_playing() -> None:
    game = _game(playtime_seconds=120)
    assert game.state == "playing"


def test_finished_game_state() -> None:
    game = _game(progress="finished", playtime_seconds=120)
    assert game.state == "finished"


def test_playing_again_clears_finished() -> None:
    game = _game(progress="finished", playtime_seconds=120)
    game.touch_play(30)
    assert game.state == "playing"


def test_state_is_saved_in_dict() -> None:
    game = _game(progress="finished")
    assert game.to_dict()["progress"] == "finished"
    assert Game.from_dict(game.to_dict()).state == "finished"
