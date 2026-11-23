from __future__ import annotations

from pathlib import Path

from umbral.detect import profile_for_rom
from umbral.profiles import PROFILES


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
