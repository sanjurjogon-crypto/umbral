from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import umbral.updater as updater
from umbral.updater import (
    UpdateError,
    UpdateInfo,
    _info_from_payload,
    _replacement_script,
    backup_data,
    download_update,
    is_newer,
    parse_version,
)


def test_parse_version_and_is_newer() -> None:
    assert parse_version("v8.21.0") == (8, 21, 0)
    assert parse_version("V8.20") == (8, 20)
    assert is_newer("8.22.0", "8.21.0") is True
    assert is_newer("8.21.0", "8.21.0") is False
    assert is_newer("8.21.0.1", "8.21.0") is True
    assert is_newer("8.20.9", "8.21.0") is False


def test_info_from_payload_extracts_exe_and_sha() -> None:
    payload = {
        "tag_name": "v8.22.0",
        "body": "Mejoras varias",
        "html_url": "https://github.com/sanjurjogon-crypto/umbral/releases/tag/v8.22.0",
        "assets": [
            {
                "name": "Umbral.exe",
                "size": 2048,
                "digest": "sha256:" + "a" * 64,
                "browser_download_url": "https://github.com/sanjurjogon-crypto/umbral/releases/download/v8.22.0/Umbral.exe",
            },
            {
                "name": "Umbral.exe.sha256",
                "browser_download_url": "https://github.com/sanjurjogon-crypto/umbral/releases/download/v8.22.0/Umbral.exe.sha256",
            },
        ],
    }
    info = _info_from_payload(payload)
    assert info is not None
    assert info.version == "8.22.0"
    assert info.digest == "sha256:" + "a" * 64
    assert info.sha_url.endswith("Umbral.exe.sha256")


def test_download_update_verifies_sha_and_rejects_missing_remote_sha(
    monkeypatch, tmp_path: Path
) -> None:
    payload = b"MZ" + b"0" * 2048
    expected_sha = hashlib.sha256(payload).hexdigest()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    def fake_download(url, target: Path, expected_size, progress, cancel_event) -> str:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return expected_sha

    monkeypatch.setattr(updater, "_download_bytes", fake_download)
    info = UpdateInfo(
        version="8.22.0",
        tag="v8.22.0",
        notes="",
        asset_url="https://github.com/example/Umbral.exe",
        asset_name="Umbral.exe",
        size=len(payload),
        digest="",
        sha_url="https://github.com/example/Umbral.exe.sha256",
        page_url="https://github.com/example/releases/tag/v8.22.0",
        published_at="",
    )

    monkeypatch.setattr(updater, "_read_sha_file", lambda _url: "")
    with pytest.raises(UpdateError, match="SHA-256"):
        download_update(info)

    monkeypatch.setattr(updater, "_read_sha_file", lambda _url: "0" * 64)
    with pytest.raises(UpdateError, match="no coincide"):
        download_update(info)

    monkeypatch.setattr(updater, "_read_sha_file", lambda _url: expected_sha)
    downloaded = download_update(info)
    assert downloaded.is_file()
    assert downloaded.read_bytes() == payload


def test_backup_data_rotates_and_keeps_latest(monkeypatch, tmp_path: Path) -> None:
    appdata = tmp_path / "roaming"
    umbral_dir = appdata / "Umbral"
    umbral_dir.mkdir(parents=True)
    (umbral_dir / "library.json").write_text('{"games": []}', encoding="utf-8")
    (umbral_dir / "settings.json").write_text('{"version": 1}', encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))

    for version in ("8.18.0", "8.19.0", "8.20.0", "8.21.0"):
        dest = backup_data(version, keep=3)
        assert (dest / "library.json").is_file()
        assert (dest / "settings.json").is_file()

    backups = sorted(item.name for item in (umbral_dir / "backups").iterdir())
    assert len(backups) == 3


def test_replacement_script_waits_stages_verifies_and_logs(tmp_path: Path) -> None:
    target = tmp_path / "Umbral.exe"
    new = tmp_path / "Umbral-8.22.0.exe"
    script = _replacement_script(target, new, 4321)
    assert "$pidToWait = 4321" in script
    assert "$staged =" in script
    assert "umbral-update.log" in script
    assert "sigue abierto" in script
    assert "HasExited" in script
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
