from __future__ import annotations

from pathlib import Path

from umbral.detect import detect, profile_for_rom
from umbral.profiles import PROFILES, profile_from_dict


def _sega_rom(path: Path, size: int = 0x4000) -> Path:
    data = bytearray(size)
    data[0x100:0x110] = b"SEGA MEGA DRIVE"
    path.write_bytes(data)
    return path


def test_valid_genesis_rom_maps_to_kega(tmp_path: Path) -> None:
    rom = _sega_rom(tmp_path / "game.bin")
    profile = profile_for_rom(rom, PROFILES)
    assert profile is not None
    assert profile.key == "kega"


def test_document_does_not_map_to_emulator(tmp_path: Path) -> None:
    doc = tmp_path / "notes.md"
    doc.write_text("documentacion", encoding="utf-8")
    assert profile_for_rom(doc, PROFILES) is None


def test_shader_data_does_not_map_to_emulator(tmp_path: Path) -> None:
    data = tmp_path / "pipelines.bin"
    data.write_bytes(bytes(range(256)) * 128)
    assert profile_for_rom(data, PROFILES) is None


def test_duplicate_rom_titles_are_preserved(monkeypatch, tmp_path: Path) -> None:
    import umbral.detect as detect_mod

    emu = tmp_path / "snes9x.exe"
    emu.write_bytes(b"MZ")
    rom1 = tmp_path / "Chrono Trigger (USA).sfc"
    rom2 = tmp_path / "Chrono Trigger (Japan).sfc"
    rom1.write_bytes(b"\x00" * 1024)
    rom2.write_bytes(b"\x00" * 1024)

    monkeypatch.setattr(detect_mod, "_default_roots", lambda: [tmp_path])
    monkeypatch.setattr(detect_mod, "store_games", lambda _folders=None: [])
    result = detect(emulator_paths={"snes9x": str(emu)}, scan_folders=[str(tmp_path)])
    roms = {game.rom_path for game in result.games}
    assert str(rom1) in roms
    assert str(rom2) in roms


def test_custom_emulator_extensions_without_dot_are_normalized() -> None:
    profile = profile_from_dict(
        {
            "key": "custom-test",
            "name": "TestEmu",
            "system_key": "gba",
            "executable": "C:/emu/test.exe",
            "rom_extensions": ["gba", ".zip"],
        }
    )
    assert profile is not None
    assert profile.rom_extensions == (".gba", ".zip")


def test_dolphin_detects_gamecube_and_wii_separately(monkeypatch, tmp_path: Path) -> None:
    import umbral.detect as detect_mod

    emu = tmp_path / "Dolphin.exe"
    emu.write_bytes(b"MZ")
    gc_rom = tmp_path / "Super Smash Bros Melee.gcm"
    gc_rom.write_bytes(b"\x00" * 128)
    wii_rom = tmp_path / "Super Mario Galaxy.iso"
    wii_data = bytearray(0x40)
    wii_data[0x18:0x1C] = b"\x5d\x1c\x9e\xa3"
    wii_rom.write_bytes(wii_data)

    monkeypatch.setattr(detect_mod, "_default_roots", lambda: [tmp_path])
    monkeypatch.setattr(detect_mod, "store_games", lambda _folders=None: [])
    result = detect(emulator_paths={"dolphin": str(emu)}, scan_folders=[str(tmp_path)])
    by_rom = {game.rom_path: game for game in result.games}
    assert by_rom[str(gc_rom)].system_key == "gamecube"
    assert by_rom[str(gc_rom)].system == "GameCube"
    assert by_rom[str(wii_rom)].system_key == "wii"
    assert by_rom[str(wii_rom)].system == "Wii"
