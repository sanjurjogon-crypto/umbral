from __future__ import annotations

import json
from pathlib import Path

import umbral.stores as stores


def _manifest(path: Path, app_id: str, name: str, install_dir: str) -> None:
    path.write_text(
        '"AppState"\n{\n'
        f'\t"appid"\t\t"{app_id}"\n'
        f'\t"name"\t\t"{name}"\n'
        f'\t"installdir"\t\t"{install_dir}"\n'
        "}\n",
        encoding="utf-8",
    )


def test_secondary_library_without_steam_exe_is_scanned(monkeypatch, tmp_path: Path) -> None:
    main = tmp_path / "main"
    secondary = tmp_path / "secondary"
    (main / "steamapps" / "common" / "GameA").mkdir(parents=True)
    (secondary / "steamapps" / "common" / "GameB").mkdir(parents=True)
    (main / "steam.exe").write_bytes(b"MZ")
    _manifest(main / "steamapps" / "appmanifest_100.acf", "100", "Game A", "GameA")
    _manifest(secondary / "steamapps" / "appmanifest_200.acf", "200", "Game B", "GameB")
    monkeypatch.setattr(stores, "steam_roots", lambda: [main, secondary])

    games = {game.title: game for game in stores.steam_games()}

    assert set(games) == {"Game A", "Game B"}
    assert games["Game B"].executable == str(main / "steam.exe")
    assert games["Game B"].arguments == ["-applaunch", "200"]
    assert games["Game B"].working_dir == str(secondary / "steamapps" / "common" / "GameB")


def test_vdf_new_format_paths(monkeypatch, tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    text = '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"' + str(library).replace("\\", "\\\\") + '"\n\t}\n}\n'
    assert stores._vdf_library_paths(text) == [library]


def test_vdf_old_format_paths(monkeypatch, tmp_path: Path) -> None:
    library = tmp_path / "old"
    library.mkdir()
    text = '"LibraryFolders"\n{\n\t"1"\t\t"' + str(library).replace("\\", "\\\\") + '"\n}\n'
    assert stores._vdf_library_paths(text) == [library]


def test_steam_tools_are_skipped(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "steam"
    (root / "steamapps" / "common" / "Steamworks Shared").mkdir(parents=True)
    (root / "steam.exe").write_bytes(b"MZ")
    _manifest(
        root / "steamapps" / "appmanifest_228980.acf",
        "228980",
        "Steamworks Common Redistributables",
        "Steamworks Shared",
    )
    monkeypatch.setattr(stores, "steam_roots", lambda: [root])
    assert stores.steam_games() == []


def test_gog_info_game_is_detected(monkeypatch, tmp_path: Path) -> None:
    game_dir = tmp_path / "Hollow Knight"
    game_dir.mkdir()
    exe = game_dir / "hollow_knight.exe"
    exe.write_bytes(b"MZ")
    info = game_dir / "goggame-1308320804.info"
    info.write_text(
        json.dumps(
            {
                "gameId": "1308320804",
                "name": "Hollow Knight",
                "playTasks": [
                    {
                        "category": "game",
                        "isPrimary": True,
                        "path": "hollow_knight.exe",
                        "arguments": "--skip-intro",
                        "workingDir": ".",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(stores, "_gog_registry_games", lambda: [])
    monkeypatch.setattr(stores, "gog_roots", lambda _folders=None: [tmp_path])

    games = stores.gog_games([str(tmp_path)])
    assert len(games) == 1
    assert games[0].title == "Hollow Knight"
    assert games[0].source == "gog"
    assert games[0].system_key == "gog"
    assert games[0].executable == str(exe)
    assert games[0].arguments == ["--skip-intro"]
