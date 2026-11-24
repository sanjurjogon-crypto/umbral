from __future__ import annotations

import json
from pathlib import Path

import umbral.store as store_module


def _point_store(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(store_module, "library_file", lambda: tmp_path / "library.json")
    monkeypatch.setattr(store_module, "settings_file", lambda: tmp_path / "settings.json")


def _sega_rom(path: Path, size: int = 0x4000) -> Path:
    data = bytearray(size)
    data[0x100:0x110] = b"SEGA MEGA DRIVE"
    path.write_bytes(data)
    return path


def _game(rom: Path, system_key: str = "genesis") -> dict:
    return {
        "id": "genesis-test",
        "title": "Test",
        "system": "Mega Drive / Genesis",
        "system_key": system_key,
        "rom_path": str(rom),
        "executable": "C:/emulador/fusion.exe",
        "source": "auto",
    }


def test_invalid_auto_entry_is_removed(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    doc = tmp_path / "notes.md"
    doc.write_text("no es rom", encoding="utf-8")
    (tmp_path / "library.json").write_text(
        json.dumps({"games": [_game(doc)]}), encoding="utf-8"
    )
    store = store_module.Store()
    assert store.games == []


def test_valid_auto_entry_is_kept(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    rom = _sega_rom(tmp_path / "game.bin")
    (tmp_path / "library.json").write_text(
        json.dumps({"games": [_game(rom)]}), encoding="utf-8"
    )
    store = store_module.Store()
    assert len(store.games) == 1


def test_missing_rom_entry_is_kept(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    missing = tmp_path / "external.bin"
    (tmp_path / "library.json").write_text(
        json.dumps({"games": [_game(missing)]}), encoding="utf-8"
    )
    store = store_module.Store()
    assert len(store.games) == 1


def test_corrupt_library_restores_backup(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    rom = _sega_rom(tmp_path / "game.bin")
    library = tmp_path / "library.json"
    library.write_text("{ esto no es json", encoding="utf-8")
    backup = tmp_path / "library.json.bak1"
    backup.write_text(
        json.dumps({"games": [_game(rom)]}), encoding="utf-8"
    )
    store = store_module.Store()
    assert len(store.games) == 1
    assert "restaurado" in store.recovery_notice


def test_write_rotates_backups(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    library = tmp_path / "library.json"
    library.write_text(json.dumps({"games": []}), encoding="utf-8")
    store_module._write_json(library, {"games": [{"id": "uno"}]})
    store_module._write_json(library, {"games": [{"id": "dos"}]})
    assert (tmp_path / "library.json.bak1").is_file()
    assert (tmp_path / "library.json.bak2").is_file()


def test_stale_cover_path_is_cleared_on_load(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    rom = _sega_rom(tmp_path / "game.bin")
    entry = _game(rom)
    entry["cover"] = str(tmp_path / "deleted-cover.jpg")
    (tmp_path / "library.json").write_text(
        json.dumps({"games": [entry]}), encoding="utf-8"
    )
    store = store_module.Store()
    assert len(store.games) == 1
    assert store.games[0].cover == ""


def test_export_and_import_library_merges_playtime_and_settings(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    store = store_module.Store()
    rom = _sega_rom(tmp_path / "game.bin")
    existing = store_module.Game.from_dict(_game(rom))
    existing.playtime_seconds = 120
    existing.sessions = 1
    store.games = [existing]
    store.settings["scan_folders"] = ["C:/Games"]
    store.save_library()
    store.save_settings()

    backup_file = tmp_path / "backup.json"
    backup_payload = {
        "version": 1,
        "games": [
            {
                **_game(rom),
                "playtime_seconds": 3600,
                "sessions": 5,
                "favorite": True,
                "progress": "finished",
                "notes": "Completado al 100%",
            },
            {
                "id": "snes-chrono",
                "title": "Chrono Trigger",
                "system": "SNES",
                "system_key": "snes",
                "executable": "C:/emulador/snes9x.exe",
                "rom_path": "C:/roms/chrono.sfc",
                "source": "manual",
            },
        ],
        "settings": {
            "scan_folders": ["C:/Games", "D:/Roms"],
            "emulator_paths": {"snes9x": "C:/emulador/snes9x.exe"},
        },
    }
    backup_file.write_text(json.dumps(backup_payload), encoding="utf-8")

    added, updated = store.import_library(backup_file)
    assert (added, updated) == (1, 1)
    assert store.get("genesis-test").playtime_seconds == 3600
    assert store.get("genesis-test").favorite is True
    assert store.get("genesis-test").notes == "Completado al 100%"
    assert store.get("snes-chrono") is not None
    assert store.settings["scan_folders"] == ["C:/Games", "D:/Roms"]

    exported = tmp_path / "exported.json"
    store.export_library(exported)
    parsed = json.loads(exported.read_text(encoding="utf-8"))
    assert len(parsed["games"]) == 2
