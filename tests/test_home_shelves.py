from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from umbral.models import Game
from umbral.ui.pages import HOME_SHELVES, shelf_games


def _game(game_id: str, **overrides) -> Game:
    data = {
        "id": game_id,
        "title": game_id.title(),
        "system": "PC",
        "system_key": "pc",
        "added_at": "2026-01-01T00:00:00+00:00",
    }
    data.update(overrides)
    return Game(**data)


def test_home_shelves_cover_every_state() -> None:
    assert [state for _label, state in HOME_SHELVES] == ["playing", "unplayed", "finished"]


def test_shelf_filters_by_state() -> None:
    games = [
        _game("unplayed"),
        _game("playing", playtime_seconds=600),
        _game("finished", progress="finished", playtime_seconds=900),
    ]
    assert [game.id for game in shelf_games(games, "playing")] == ["playing"]
    assert [game.id for game in shelf_games(games, "unplayed")] == ["unplayed"]
    assert [game.id for game in shelf_games(games, "finished")] == ["finished"]


def test_unplayed_shelf_orders_by_newest_addition() -> None:
    games = [
        _game("old", added_at="2025-01-01T00:00:00+00:00"),
        _game("new", added_at="2026-06-01T00:00:00+00:00"),
        _game("middle", added_at="2025-09-01T00:00:00+00:00"),
    ]
    assert [game.id for game in shelf_games(games, "unplayed")] == ["new", "middle", "old"]


def test_playing_shelf_orders_by_playtime() -> None:
    games = [
        _game("short", playtime_seconds=120),
        _game("long", playtime_seconds=7200),
        _game("medium", playtime_seconds=600),
    ]
    assert [game.id for game in shelf_games(games, "playing")] == ["long", "medium", "short"]


def test_finished_shelf_orders_by_last_session() -> None:
    games = [
        _game("older", progress="finished", last_played="2025-01-01T00:00:00+00:00"),
        _game("recent", progress="finished", last_played="2026-01-01T00:00:00+00:00"),
    ]
    assert [game.id for game in shelf_games(games, "finished")] == ["recent", "older"]


def test_shelf_respects_limit() -> None:
    games = [_game(f"game-{index}", playtime_seconds=index) for index in range(12)]
    assert len(shelf_games(games, "playing", limit=5)) == 5
