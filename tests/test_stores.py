from __future__ import annotations

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
