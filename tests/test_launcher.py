from __future__ import annotations

from pathlib import Path

import umbral.launcher as launcher
from umbral.launcher import SteamWatcher, build_command, steam_app_id
from umbral.models import Game


def _game(**overrides) -> Game:
    data = {
        "id": "test",
        "title": "Test",
        "system": "SNES",
        "system_key": "snes",
        "executable": "C:/emuladores/snes9x.exe",
        "rom_path": "C:/roms/game.sfc",
        "arguments": [],
    }
    data.update(overrides)
    return Game(**data)


def test_command_adds_rom_when_arguments_are_empty() -> None:
    command = build_command(_game(arguments=[]))
    assert command == ["C:/emuladores/snes9x.exe", "C:/roms/game.sfc"]


def test_command_replaces_placeholder() -> None:
    command = build_command(_game(arguments=["--fullscreen", "{rom}"]))
    assert command == ["C:/emuladores/snes9x.exe", "--fullscreen", "C:/roms/game.sfc"]


def test_command_does_not_duplicate_rom() -> None:
    command = build_command(_game(arguments=["{rom}"]))
    assert command.count("C:/roms/game.sfc") == 1


def test_pc_game_does_not_get_rom_argument() -> None:
    game = _game(
        system="PC",
        system_key="pc",
        rom_path="",
        executable="C:/Games/Game/Game.exe",
        arguments=[],
    )
    assert build_command(game) == ["C:/Games/Game/Game.exe"]


def test_manual_emulated_game_gets_rom_argument() -> None:
    game = _game(
        source="manual",
        arguments=[],
    )
    assert build_command(game) == ["C:/emuladores/snes9x.exe", "C:/roms/game.sfc"]


def test_manual_game_with_custom_argument_keeps_rom_once() -> None:
    game = _game(source="manual", arguments=["--fullscreen"])
    command = build_command(game)
    assert command == ["C:/emuladores/snes9x.exe", "--fullscreen", "C:/roms/game.sfc"]


def test_steam_app_id_reads_arguments_and_notes() -> None:
    from_args = _game(source="steam", arguments=["-applaunch", "570940"], notes="")
    assert steam_app_id(from_args) == "570940"
    from_notes = _game(source="steam", arguments=[], notes="AppID de Steam: 246620")
    assert steam_app_id(from_notes) == "246620"


def test_steam_watcher_tracks_running_session(monkeypatch, tmp_path: Path) -> None:
    states = iter([(False, False), (True, False), (True, False), (False, False)])
    monkeypatch.setattr(launcher, "_steam_app_state", lambda _id: next(states, (False, False)))

    watcher = SteamWatcher(
        "570940",
        tmp_path / "ds.log",
        game_id="pc-steam-570940",
        launch_timeout=2.0,
        poll_interval=0.01,
    )
    results: list[tuple[int, int, str]] = []
    watcher.finished_ok.connect(lambda code, sec, path: results.append((code, sec, path)))
    watcher.run()

    assert len(results) == 1
    assert results[0][0] == 0
    assert results[0][1] >= 1
    assert results[0][2] == str(tmp_path / "ds.log")
