from __future__ import annotations

from pathlib import Path

import pytest

import umbral.updater as updater
from umbral.updater import UpdateError, UpdateInfo, _replacement_script, download_update


def test_replacement_script_waits_and_logs(tmp_path: Path) -> None:
    target = tmp_path / "Umbral.exe"
    new = tmp_path / "Umbral-8.20.0.exe"
    script = _replacement_script(target, new, 4321)
    assert "$pidToWait = 4321" in script
    assert "umbral-update.log" in script
    assert "sigue abierto" in script
    assert "Restaurado el ejecutable anterior" in script


def test_untrusted_asset_url_is_rejected(tmp_path: Path) -> None:
    info = UpdateInfo(
        version="9.0.0",
        tag="v9.0.0",
        notes="",
        asset_url="https://evil.example/Umbral.exe",
        asset_name="Umbral.exe",
        size=2048,
        digest="",
        sha_url="",
        page_url="https://github.com/sanjurjogon-crypto/umbral/releases/tag/v9.0.0",
        published_at="",
    )
    with pytest.raises(UpdateError):
        download_update(info)


def test_missing_sha_file_raises_update_error(monkeypatch, tmp_path: Path) -> None:
    exe = tmp_path / "Umbral-9.0.0.exe"
    monkeypatch.setattr(updater, "update_dir", lambda: tmp_path)
    monkeypatch.setattr(updater, "_download_bytes", lambda *a, **kw: "a" * 64)
    monkeypatch.setattr(updater, "_read_sha_file", lambda _url: "")
    info = UpdateInfo(
        version="9.0.0",
        tag="v9.0.0",
        notes="",
        asset_url="https://github.com/sanjurjogon-crypto/umbral/releases/download/v9.0.0/Umbral.exe",
        asset_name="Umbral.exe",
        size=2048,
        digest="",
        sha_url="https://github.com/sanjurjogon-crypto/umbral/releases/download/v9.0.0/Umbral.exe.sha256",
        page_url="https://github.com/sanjurjogon-crypto/umbral/releases/tag/v9.0.0",
        published_at="",
    )
    with pytest.raises(UpdateError):
        download_update(info)
    assert not exe.exists()
