from __future__ import annotations

from pathlib import Path

from umbral.downloads import emulator_for


def _sega_rom(path: Path, size: int = 0x4000) -> Path:
    data = bytearray(size)
    data[0x100:0x110] = b"SEGA MEGA DRIVE"
    path.write_bytes(data)
    return path


def test_genesis_bin_maps_to_kega(tmp_path: Path) -> None:
    rom = _sega_rom(tmp_path / "game.bin")
    profile = emulator_for(rom)
    assert profile is not None
    assert profile.key == "kega"


def test_invalid_bin_has_no_emulator(tmp_path: Path) -> None:
    data = tmp_path / "shader.bin"
    data.write_bytes(bytes(range(256)) * 64)
    assert emulator_for(data) is None


def test_snes_rom_maps_to_snes9x(tmp_path: Path) -> None:
    rom = tmp_path / "game.sfc"
    rom.write_bytes(b"\x00" * 4096)
    profile = emulator_for(rom)
    assert profile is not None
    assert profile.key == "snes9x"
