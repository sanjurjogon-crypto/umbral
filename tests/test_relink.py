from __future__ import annotations

from pathlib import Path

from umbral.models import Game
from umbral.relink import missing_parts, relink


def _game(**overrides) -> Game:
    data = {
        "id": "test",
        "title": "Test",
        "system": "SNES",
        "system_key": "snes",
        "executable": "C:/emuladores/snes9x.exe",
        "rom_path": "C:/roms/game.sfc",
        "working_dir": "C:/emuladores",
    }
    data.update(overrides)
    return Game(**data)


def test_missing_parts_detects_rom(tmp_path: Path) -> None:
    game = _game(rom_path=str(tmp_path / "no-existe.sfc"), executable="")
    assert "rom" in missing_parts(game)
    assert "executable" in missing_parts(game)


def test_relink_updates_rom(tmp_path: Path) -> None:
    rom = tmp_path / "juego.sfc"
    rom.write_bytes(b"\x00" * 4096)
    game = _game(rom_path=str(tmp_path / "viejo.sfc"))
    assert relink(game, "rom", rom) is True
    assert game.rom_path == str(rom)
    assert "rom" not in missing_parts(game)


def test_relink_updates_executable_and_working_dir(tmp_path: Path) -> None:
    exe = tmp_path / "emulador.exe"
    exe.write_bytes(b"MZ")
    game = _game(executable="", working_dir="")
    assert relink(game, "executable", exe) is True
    assert game.executable == str(exe)
    assert game.working_dir == str(tmp_path)


def test_relink_rejects_missing_file(tmp_path: Path) -> None:
    game = _game()
    assert relink(game, "rom", tmp_path / "no-existe.sfc") is False


def test_relink_unfinished_keeps_other_missing_part(tmp_path: Path) -> None:
    rom = tmp_path / "juego.sfc"
    rom.write_bytes(b"\x00" * 4096)
    game = _game(rom_path=str(tmp_path / "viejo.sfc"), executable="")
    relink(game, "rom", rom)
    assert missing_parts(game) == ["executable"]
