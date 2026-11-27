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
            {
                "name": "Umbral-linux-x86_64",
                "size": 4096,
                "digest": "sha256:" + "b" * 64,
                "browser_download_url": "https://github.com/sanjurjogon-crypto/umbral/releases/download/v8.22.0/Umbral-linux-x86_64",
            },
            {
                "name": "Umbral-linux-x86_64.sha256",
                "browser_download_url": "https://github.com/sanjurjogon-crypto/umbral/releases/download/v8.22.0/Umbral-linux-x86_64.sha256",
            },
            {
                "name": "Umbral-macos-arm64.zip",
                "size": 5120,
                "digest": "sha256:" + "c" * 64,
                "browser_download_url": "https://github.com/sanjurjogon-crypto/umbral/releases/download/v8.22.0/Umbral-macos-arm64.zip",
            },
            {
                "name": "Umbral-macos-arm64.zip.sha256",
                "browser_download_url": "https://github.com/sanjurjogon-crypto/umbral/releases/download/v8.22.0/Umbral-macos-arm64.zip.sha256",
            },
        ],
    }
    win_info = _info_from_payload(payload, asset_name="Umbral.exe")
    assert win_info is not None
    assert win_info.version == "8.22.0"
    assert win_info.asset_name == "Umbral.exe"
    assert win_info.digest == "sha256:" + "a" * 64
    assert win_info.sha_url.endswith("Umbral.exe.sha256")

    linux_info = _info_from_payload(payload, asset_name="Umbral-linux-x86_64")
    assert linux_info is not None
    assert linux_info.asset_name == "Umbral-linux-x86_64"
    assert linux_info.digest == "sha256:" + "b" * 64
    assert linux_info.sha_url.endswith("Umbral-linux-x86_64.sha256")

    default_info = _info_from_payload(payload)
    assert default_info is not None
    assert default_info.asset_name == updater.expected_asset_name()


def test_download_update_verifies_sha_and_rejects_missing_remote_sha(
    monkeypatch, tmp_path: Path
) -> None:
    payload = b"MZ" + b"0" * 2048
    expected_sha = hashlib.sha256(payload).hexdigest()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    def fake_download(url, target: Path, expected_size, progress, cancel_event, is_pe: bool = True) -> str:
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
    monkeypatch.setenv("UMBRAL_DATA_DIR", str(umbral_dir))

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
    assert "Target-Processes-Running" in script
    assert "Move-WithRetry" in script
    assert "Copy-WithRetry" in script
    assert "Copy-Item" in script
    assert "Unblock-File" in script
    assert "--relaunch" in script
    assert "-WorkingDirectory $targetDir" in script
    assert "Start-TargetAndVerify" in script
    assert "Get-Process -Name $exeName" in script
    assert "umbral-update.log" in script
    assert "sigue abierto" in script
    assert "HasExited" in script
    assert "Restaurado el ejecutable anterior" in script


def test_fetch_covers_respects_stop_event(monkeypatch, tmp_path: Path) -> None:
    import threading
    from umbral.covers import fetch_covers
    from umbral.models import Game

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    called = 0

    def fake_fetch(game, cache=None):
        nonlocal called
        called += 1
        return None

    monkeypatch.setattr("umbral.covers.fetch_cover", fake_fetch)
    stop = threading.Event()
    stop.set()
    games = [Game(id="g1", title="Zelda", system="Nintendo 3DS", system_key="3ds", rom_path="a.3ds", emulator="azahar")]
    results, errors = fetch_covers(games, missing_only=False, stop_event=stop)
    assert results == {}
    assert errors == {}
    assert called == 0


@pytest.mark.skipif(updater.os.name != "nt", reason="Windows-specific creationflags")
def test_apply_update_on_windows_uses_create_no_window_not_detached(monkeypatch, tmp_path: Path) -> None:
    import subprocess

    target_exe = tmp_path / "Umbral (1).exe"
    new_exe = tmp_path / "Umbral-new.exe"
    target_exe.write_bytes(b"MZ" + b"\x00" * 64)
    new_exe.write_bytes(b"MZ" + b"\x00" * 64)

    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.sys, "executable", str(target_exe))
    monkeypatch.setattr(updater.shutil, "which", lambda name: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" if "powershell" in name else None)

    captured: dict[str, object] = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(updater.subprocess, "Popen", fake_popen)
    updater.apply_update(new_exe)

    flags = captured["kwargs"]["creationflags"]  # type: ignore[index]
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    detached = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    assert flags & create_no_window == create_no_window
    assert flags & detached == 0


def test_posix_replacement_script_and_elf_download(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "Umbral-linux-x86_64"
    new_bin = tmp_path / "Umbral-8.27.0-linux"
    script = updater._posix_replacement_script(target, new_bin, 9876)
    assert "PID=9876" in script
    assert "--relaunch" in script
    assert "chmod 755" in script
    assert "umbral-update.log" in script

    elf_payload = b"\x7fELF" + b"\x00" * 2048
    expected_sha = hashlib.sha256(elf_payload).hexdigest()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "cache"))

    def fake_download(url, target_path: Path, expected_size, progress, cancel_event, is_pe=True) -> str:
        assert is_pe is False
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(elf_payload)
        return expected_sha

    monkeypatch.setattr(updater, "_download_bytes", fake_download)
    monkeypatch.setattr(updater, "_read_sha_file", lambda _url: expected_sha)
    info = UpdateInfo(
        version="8.27.0",
        tag="v8.27.0",
        notes="",
        asset_url="https://github.com/example/Umbral-linux-x86_64",
        asset_name="Umbral-linux-x86_64",
        size=len(elf_payload),
        digest="",
        sha_url="https://github.com/example/Umbral-linux-x86_64.sha256",
        page_url="https://github.com/example/releases/tag/v8.27.0",
        published_at="",
    )
    out = download_update(info)
    assert out.name == "Umbral-8.27.0-linux"
    assert out.read_bytes() == elf_payload


def test_clean_subprocess_env_strips_pyinstaller_vars() -> None:
    cleaned = updater._clean_subprocess_env(
        {
            "PATH": "C:\\Windows",
            "_MEIPASS": "C:\\temp\\_MEI1",
            "_MEIPASS2": "C:\\temp\\_MEI2",
            "_PYI_ARCHIVE_FILE": "C:\\app\\Umbral.exe",
            "_PYI_PARENT_PROCESS_LEVEL": "1",
            "TCL_LIBRARY": "C:\\temp\\_MEI1\\tcl",
            "TK_LIBRARY": "C:\\temp\\_MEI1\\tk",
            "LOCALAPPDATA": "C:\\Users\\x\\AppData\\Local",
        }
    )
    assert cleaned["PATH"] == "C:\\Windows"
    assert cleaned["LOCALAPPDATA"] == "C:\\Users\\x\\AppData\\Local"
    for key in ("_MEIPASS", "_MEIPASS2", "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL", "TCL_LIBRARY", "TK_LIBRARY"):
        assert key not in cleaned


def test_download_bytes_retries_transient_error_and_reports_progress(monkeypatch, tmp_path: Path) -> None:
    from urllib.error import URLError

    payload = b"MZ" + b"x" * 2048
    calls = 0

    class FakeResponse:
        headers = {"Content-Length": str(len(payload))}

        def __init__(self) -> None:
            self._offset = 0

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def read(self, size: int) -> bytes:
            if self._offset >= len(payload):
                return b""
            chunk = payload[self._offset : self._offset + size]
            self._offset += len(chunk)
            return chunk

    def fake_urlopen(request, timeout=18.0, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError("temporary glitch")
        return FakeResponse()

    monkeypatch.setattr(updater, "urlopen", fake_urlopen)
    events: list[tuple[int, int]] = []
    target = tmp_path / "Umbral-8.23.1.exe"
    sha = updater._download_bytes(
        "https://github.com/sanjurjogon-crypto/umbral/releases/download/v8.23.1/Umbral.exe",
        target,
        len(payload),
        lambda done, total: events.append((done, total)),
        None,
    )
    assert calls == 2
    assert target.read_bytes() == payload
    assert sha == hashlib.sha256(payload).hexdigest()
    assert events[0] == (0, len(payload))
    assert events[-1] == (len(payload), len(payload))
    assert updater.format_download_progress(5 * 1024 * 1024, 10 * 1024 * 1024) == "50 % · 5,0 de 10,0 MB"


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
