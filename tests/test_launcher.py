from __future__ import annotations

from pathlib import Path

from umbral.launcher import build_command
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
