from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from umbral.covers import (
    _candidate_titles,
    _gamedb_cover,
    image_size,
    is_image_bytes,
    upscale_cover_bytes,
)
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


def test_upscale_cover_bytes_upscales_low_res_and_keeps_hd(tmp_path: Path) -> None:
    low_buf = io.BytesIO()
    Image.new("RGB", (264, 374), (120, 40, 200)).save(low_buf, format="JPEG", quality=90)
    low_raw = low_buf.getvalue()

    upscaled = upscale_cover_bytes(low_raw)
    assert upscaled != low_raw
    out_file = tmp_path / "up.jpg"
    out_file.write_bytes(upscaled)
    new_w, new_h = image_size(out_file)
    assert new_w >= 600
    assert new_h >= 800

    hd_buf = io.BytesIO()
    Image.new("RGB", (600, 900), (30, 140, 90)).save(hd_buf, format="JPEG", quality=90)
    hd_raw = hd_buf.getvalue()
    assert upscale_cover_bytes(hd_raw) == hd_raw


def test_gamedb_cover_prefers_2x_before_big(monkeypatch) -> None:
    import umbral.covers as covers_mod

    monkeypatch.setattr(
        covers_mod,
        "_request_json",
        lambda url, limit=3_000_000: {
            "name": "Zelda",
            "platforms": [130],
            "cover": {"url": "//images.igdb.com/igdb/image/upload/t_thumb/co1234.jpg"},
        },
    )
    info = _gamedb_cover("1", [130])
    assert info is not None
    assert info["url"].endswith("/t_cover_big_2x/co1234.jpg")
    assert info["urls"][1].endswith("/t_cover_big/co1234.jpg")
