from __future__ import annotations

import zipfile
from pathlib import Path

from umbral.rom_rules import (
    rom_system,
    sega_header,
    validate_rom,
    zip_has_rom,
    zip_rom_system,
)


def _sega_rom(path: Path, size: int = 0x4000) -> Path:
    data = bytearray(size)
    data[0x100:0x110] = b"SEGA MEGA DRIVE"
    path.write_bytes(data)
    return path


def test_sega_header_accepts_genesis(tmp_path: Path) -> None:
    rom = _sega_rom(tmp_path / "game.bin")
    assert sega_header(rom) is True
    assert rom_system(rom) == "genesis"
    assert validate_rom(rom, "genesis") is True


def test_markdown_is_rejected(tmp_path: Path) -> None:
    doc = tmp_path / "notes.md"
    doc.write_text("# Notas\n\nEsto no es una ROM.\n", encoding="utf-8")
    assert rom_system(doc) is None
    assert validate_rom(doc, "genesis") is False


def test_binary_data_is_rejected(tmp_path: Path) -> None:
    data = tmp_path / "shader.bin"
    data.write_bytes(bytes(range(256)) * 64)
    assert rom_system(data) is None
    assert validate_rom(data, "genesis") is False


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "missing.bin"
    assert validate_rom(missing, "genesis") is False


def test_zip_with_rom_is_detected(tmp_path: Path) -> None:
    inner = tmp_path / "smw.sfc"
    inner.write_bytes(b"\x00" * 1024)
    archive = tmp_path / "snes.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.write(inner, arcname="smw.sfc")
    assert zip_has_rom(archive) is True
    assert zip_rom_system(archive) == "snes"


def test_zip_with_only_documents_is_rejected(tmp_path: Path) -> None:
    inner = tmp_path / "readme.txt"
    inner.write_text("no es una rom", encoding="utf-8")
    archive = tmp_path / "docs.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.write(inner, arcname="readme.txt")
    assert zip_has_rom(archive) is False
    assert validate_rom(archive, "") is False


def test_gamecube_and_wii_discs_are_distinguished(tmp_path: Path) -> None:
    gc_iso = tmp_path / "disc_a.iso"
    gc_data = bytearray(0x40)
    gc_data[0x1C:0x20] = b"\xc2\x33\x9f\x3d"
    gc_iso.write_bytes(gc_data)
    assert rom_system(gc_iso) == "gamecube"

    wii_iso = tmp_path / "disc_b.iso"
    wii_data = bytearray(0x40)
    wii_data[0x18:0x1C] = b"\x5d\x1c\x9e\xa3"
    wii_iso.write_bytes(wii_data)
    assert rom_system(wii_iso) == "wii"

    gcm = tmp_path / "Melee.gcm"
    gcm.write_bytes(b"\x00" * 64)
    assert rom_system(gcm) == "gamecube"

    rvz_gc = tmp_path / "WindWaker.rvz"
    rvz_data = bytearray(0x80)
    rvz_data[0:4] = b"RVZ\x01"
    rvz_data[0x74:0x78] = b"\xc2\x33\x9f\x3d"
    rvz_gc.write_bytes(rvz_data)
    assert rom_system(rvz_gc) == "gamecube"
