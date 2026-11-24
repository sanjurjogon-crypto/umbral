from __future__ import annotations

from pathlib import Path

from umbral.covers import _candidate_titles, image_size, is_image_bytes
from umbral.models import Game


def _game(**overrides) -> Game:
    data = {
        "id": "test",
        "title": "PONFERRADA IA",
        "system": "Mega Drive / Genesis",
        "system_key": "genesis",
        "rom_path": "",
        "executable": "",
    }
    data.update(overrides)
    return Game(**data)


def test_emulated_game_prefers_rom_over_emulator() -> None:
    game = _game(
        rom_path=r"C:\Roms\Street Voter II Turbo.bin",
        executable=r"C:\Emuladores\azahar.exe",
    )
    titles = _candidate_titles(game)
    assert titles[0] == "Street Voter II Turbo"
    assert "azahar" not in " ".join(titles).lower()


def test_pc_game_can_use_executable() -> None:
    game = _game(
        title="Hades",
        system="PC",
        system_key="pc",
        executable=r"C:\Games\Hades\Hades.exe",
    )
    titles = _candidate_titles(game)
    assert titles[0] == "Hades"


def test_emulated_game_without_rom_still_returns_title() -> None:
    game = _game(title="Sonic", executable=r"C:\Emuladores\fusion.exe")
    assert _candidate_titles(game)[0] == "Sonic"


def test_html_response_is_not_a_cover() -> None:
    assert is_image_bytes(b"<!DOCTYPE html><html><body>404</body></html>") is False


def test_png_and_jpeg_are_covers() -> None:
    assert is_image_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32) is True
    assert is_image_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32) is True


def test_webp_image_size_is_parsed(tmp_path: Path) -> None:
    # Minimal VP8X header: 600x900 (stored as dimension - 1 in 24-bit little-endian)
    payload = bytearray(30)
    payload[0:4] = b"RIFF"
    payload[8:16] = b"WEBPVP8X"
    payload[24:27] = (599).to_bytes(3, "little")
    payload[27:30] = (899).to_bytes(3, "little")
    img = tmp_path / "cover.webp"
    img.write_bytes(payload)
    assert is_image_bytes(payload) is True
    assert image_size(img) == (600, 900)
