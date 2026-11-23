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
