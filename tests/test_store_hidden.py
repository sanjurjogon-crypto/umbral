from __future__ import annotations

import json
from pathlib import Path

import umbral.store as store_module
from umbral.models import Game


def _point_store(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(store_module, "library_file", lambda: tmp_path / "library.json")
    monkeypatch.setattr(store_module, "settings_file", lambda: tmp_path / "settings.json")


def _game(game_id: str, **overrides) -> Game:
    data = {
        "id": game_id,
        "title": game_id,
        "system": "Mega Drive / Genesis",
        "system_key": "genesis",
        "rom_path": f"C:/roms/{game_id}.bin",
        "executable": "C:/emuladores/fusion.exe",
        "source": "auto",
    }
    data.update(overrides)
    return Game(**data)


def test_hiding_one_rom_keeps_other_games_of_same_emulator(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    store = store_module.Store()
    store.games = [_game("sonic"), _game("streets-of-rage")]
    store.save_library()

    store.hide("sonic")
    store.save_library()

    reloaded = store_module.Store()
    assert [game.id for game in reloaded.games] == ["streets-of-rage"]
    assert "c:/emuladores/fusion.exe" not in reloaded.settings["hidden_paths"]


def test_hiding_pc_game_keeps_executable_hidden(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    store = store_module.Store()
    game = _game(
        "hades",
        system="PC",
        system_key="pc",
        rom_path="",
        executable="C:/Games/Hades/Hades.exe",
        source="standalone",
    )
    store.games = [game]
    store.hide("hades")

    assert store.settings["hidden_paths"]
    reloaded = store_module.Store()
    assert reloaded.games == []


def test_merge_does_not_return_hidden_pc_game(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    store = store_module.Store()
    game = _game(
        "hades",
        system="PC",
        system_key="pc",
        rom_path="",
        executable="C:/Games/Hades/Hades.exe",
        source="standalone",
    )
    store.hide(game.id)
    store.merge_detected([game])
    assert store.games == []


def test_recovered_backup_is_not_overwritten_by_corrupt_file(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    library = tmp_path / "library.json"
    backup = tmp_path / "library.json.bak1"
    backup.write_text(json.dumps({"games": [{"id": "uno"}]}), encoding="utf-8")
    library.write_text("{ roto", encoding="utf-8")

    store_module._write_json(library, {"games": [{"id": "dos"}]})

    assert json.loads(backup.read_text(encoding="utf-8"))["games"] == [{"id": "uno"}]


def test_manual_port_is_not_duplicated_by_detection(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    store = store_module.Store()
    manual = _game(
        "ports-miport-manual",
        title="Mi Port",
        system="Ports",
        system_key="ports",
        rom_path="",
        executable="C:/ports/miport.exe",
        arguments=["--custom"],
        source="manual",
    )
    store.games = [manual]
    detected = _game(
        "ports-miport",
        title="Mi Port",
        system="Ports",
        system_key="ports",
        rom_path="C:/roms/miport.rvz",
        executable="C:/ports/miport.exe",
        arguments=["-e", "{rom}"],
    )
    store.merge_detected([detected])
    assert len(store.games) == 1
    assert store.games[0].id == "ports-miport-manual"
    assert store.games[0].arguments == ["--custom"]
    assert store.games[0].rom_path == "C:/roms/miport.rvz"


def test_detection_does_not_overwrite_manual_title(monkeypatch, tmp_path: Path) -> None:
    _point_store(monkeypatch, tmp_path)
    store = store_module.Store()
    manual = _game(
        "genesis-sonic-manual",
        title="Sonic el Erizo",
        system="Mega Drive / Genesis",
        system_key="genesis",
        rom_path="C:/roms/sonic.bin",
        executable="C:/emuladores/fusion.exe",
        source="manual",
        description="Mi descripcion",
    )
    store.games = [manual]
    detected = _game(
        "genesis-sonic",
        title="Sonic the Hedgehog",
        system="Mega Drive / Genesis",
        system_key="genesis",
        rom_path="C:/roms/sonic.bin",
        executable="C:/emuladores/fusion.exe",
        description="Automatica",
    )
    store.merge_detected([detected])
    assert len(store.games) == 1
    assert store.games[0].title == "Sonic el Erizo"
    assert store.games[0].description == "Mi descripcion"
