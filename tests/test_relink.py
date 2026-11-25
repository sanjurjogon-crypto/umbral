from __future__ import annotations

from pathlib import Path

from umbral.models import Emulator, Game
from umbral.relink import is_installed, missing_parts, relink, relocate_missing_paths
import umbral.store as store_module


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


def test_is_installed_handles_steam_store_pc_and_rom(tmp_path: Path) -> None:
    steam_exe = tmp_path / "steam.exe"
    steam_exe.write_bytes(b"MZ")
    steam_dir = tmp_path / "steamapps" / "common" / "EldenRing"
    steam_dir.mkdir(parents=True)
    steam_game = Game(
        id="pc-steam-1245620",
        title="ELDEN RING",
        system="Steam",
        system_key="steam",
        executable=str(steam_exe),
        working_dir=str(steam_dir),
        source="steam",
    )
    assert is_installed(steam_game, detected_ids={"pc-steam-1245620"}) is True
    # Steam left folder behind after uninstalling manifest
    assert is_installed(steam_game, detected_ids=set()) is False

    epic_dir = tmp_path / "Fortnite"
    epic_dir.mkdir()
    epic_exe = epic_dir / "FortniteLauncher.exe"
    epic_exe.write_bytes(b"MZ")
    epic_game = Game(
        id="pc-epic-fortnite",
        title="Fortnite",
        system="Epic Games",
        system_key="epic",
        executable=str(epic_exe),
        working_dir=str(epic_dir),
        source="epic",
    )
    assert is_installed(epic_game) is True
    epic_exe.unlink()
    assert is_installed(epic_game) is False

    rom = tmp_path / "mario.sfc"
    rom.write_bytes(b"\x00" * 16)
    emu = tmp_path / "snes9x.exe"
    emu.write_bytes(b"MZ")
    rom_game = _game(rom_path=str(rom), executable=str(emu))
    assert is_installed(rom_game) is True
    rom.unlink()
    assert is_installed(rom_game) is False


def test_relocate_missing_paths_updates_moved_pc_rom_and_emulator(tmp_path: Path) -> None:
    scan_dir = tmp_path / "Games"
    celeste_dir = scan_dir / "Celeste"
    celeste_dir.mkdir(parents=True)
    new_pc_exe = celeste_dir / "Celeste.exe"
    new_pc_exe.write_bytes(b"MZ")

    # Generic launcher stem in a different folder name should NOT falsely relink
    other_dir = scan_dir / "OtherGame"
    other_dir.mkdir()
    wrong_generic = other_dir / "game.exe"
    wrong_generic.write_bytes(b"MZ")

    snes_dir = scan_dir / "SNES"
    snes_dir.mkdir()
    new_rom = snes_dir / "SuperMetroid.sfc"
    new_rom.write_bytes(b"\x00" * 64)
    new_emu = tmp_path / "Emulators" / "snes9x-new.exe"
    new_emu.parent.mkdir()
    new_emu.write_bytes(b"MZ")

    moved_pc = Game(
        id="pc-celeste",
        title="Celeste",
        system="PC",
        system_key="pc",
        executable=str(tmp_path / "Old" / "Celeste" / "Celeste.exe"),
        working_dir=str(tmp_path / "Old" / "Celeste"),
        source="standalone",
    )
    uninstalled_generic = Game(
        id="pc-missing-generic",
        title="Missing Game",
        system="PC",
        system_key="pc",
        executable=str(tmp_path / "GoneGame" / "game.exe"),
        working_dir=str(tmp_path / "GoneGame"),
        source="standalone",
    )
    moved_rom_game = Game(
        id="snes-metroid",
        title="Super Metroid",
        system="SNES",
        system_key="snes",
        emulator="Snes9x",
        executable=str(tmp_path / "OldEmu" / "snes9x.exe"),
        rom_path=str(tmp_path / "Downloads" / "SuperMetroid.sfc"),
        working_dir=str(tmp_path / "OldEmu"),
        source="manual",
    )

    emus = [
        Emulator(
            key="snes9x",
            name="Snes9x",
            executable=str(new_emu),
            system="SNES",
            system_key="snes",
            found=True,
        )
    ]
    updated = relocate_missing_paths(
        [moved_pc, uninstalled_generic, moved_rom_game],
        emulators=emus,
        scan_folders=[str(scan_dir)],
    )
    assert updated == 2
    assert moved_pc.executable == str(new_pc_exe)
    assert moved_pc.working_dir == str(celeste_dir)
    assert uninstalled_generic.executable == str(tmp_path / "GoneGame" / "game.exe")
    assert moved_rom_game.rom_path == str(new_rom)
    assert moved_rom_game.executable == str(new_emu)
    assert moved_rom_game.working_dir == str(new_emu.parent)


def test_store_prune_missing_removes_without_hiding(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(store_module, "library_file", lambda: tmp_path / "library.json")
    monkeypatch.setattr(store_module, "settings_file", lambda: tmp_path / "settings.json")
    store = store_module.Store()

    keep_exe = tmp_path / "Kept.exe"
    keep_exe.write_bytes(b"MZ")
    kept = Game(id="kept", title="Kept", system="PC", system_key="pc", executable=str(keep_exe), source="standalone")
    gone = Game(
        id="gone",
        title="Uninstalled",
        system="PC",
        system_key="pc",
        executable=str(tmp_path / "Uninstalled.exe"),
        source="standalone",
    )
    store.games = [kept, gone]

    removed = store.prune_missing(detected_ids=set())
    assert [g.id for g in removed] == ["gone"]
    assert [g.id for g in store.games] == ["kept"]
    assert store.settings["hidden_games"] == []
    assert store.settings["hidden_paths"] == []
