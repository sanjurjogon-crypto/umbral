from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLabel

import umbral.store as store_module
from umbral.models import Emulator, Game
from umbral.ui.dialogs import AddGameDialog
from umbral.ui.pages import HealthPage, LibraryPage
from umbral.ui.shelf import ShelfCanvas


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _store(monkeypatch, tmp_path: Path, games: list[Game]) -> store_module.Store:
    monkeypatch.setattr(store_module, "library_file", lambda: tmp_path / "library.json")
    monkeypatch.setattr(store_module, "settings_file", lambda: tmp_path / "settings.json")
    store = store_module.Store()
    store.games = games
    return store


def test_library_search_matches_system_emulator_and_notes(monkeypatch, tmp_path: Path) -> None:
    _app()
    games = [
        Game(id="g1", title="Zelda", system="Wii / GameCube", system_key="wii", emulator="Dolphin", notes="Master Quest"),
        Game(id="g2", title="Hades", system="PC", system_key="pc", emulator="Standalone", notes="Roguelike"),
    ]
    page = LibraryPage(_store(monkeypatch, tmp_path, games))
    page.set_query("dolphin")
    assert [g.id for g in page._visible_games()] == ["g1"]
    page.set_query("roguelike")
    assert [g.id for g in page._visible_games()] == ["g2"]


def test_library_sort_puts_missing_years_last(monkeypatch, tmp_path: Path) -> None:
    _app()
    games = [
        Game(id="no-year", title="Alpha", system="PC", system_key="pc", year=None),
        Game(id="y2000", title="Beta", system="PC", system_key="pc", year=2000),
        Game(id="y1998", title="Gamma", system="PC", system_key="pc", year=1998),
    ]
    page = LibraryPage(_store(monkeypatch, tmp_path, games))
    page._sort_key = "year"
    page._sort_asc = True
    assert [g.id for g in page._visible_games()] == ["y1998", "y2000", "no-year"]
    page._sort_asc = False
    assert [g.id for g in page._visible_games()] == ["y2000", "y1998", "no-year"]


def test_add_game_dialog_saves_custom_cover_notes_and_clears_pc_rom(tmp_path: Path) -> None:
    _app()
    exe = tmp_path / "MyGame.exe"
    exe.write_bytes(b"MZ")
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    dialog = AddGameDialog()
    dialog.rom_edit.setText(str(exe))
    dialog._auto_fill()
    dialog.title_edit.setText("My Game")
    dialog.cover_edit.setText(str(cover))
    dialog.notes_edit.setPlainText("Custom note")
    dialog.playtime_spin.setValue(90)
    idx = dialog.progress_combo.findData("finished")
    dialog.progress_combo.setCurrentIndex(idx)
    dialog._save()

    game = dialog.game()
    assert game is not None
    assert game.executable == str(exe)
    assert game.rom_path == ""
    assert game.cover == str(cover)
    assert game.notes == "Custom note"
    assert game.playtime_seconds == 5400
    assert game.state == "finished"


def test_shelf_canvas_home_end_and_page_navigation() -> None:
    _app()
    canvas = ShelfCanvas()
    games = [Game(id=f"g{i}", title=f"Game {i}", system="PC", system_key="pc") for i in range(10)]
    canvas.set_games(games)
    assert canvas.index == 0

    canvas.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_End, Qt.NoModifier))
    assert canvas.index == 9
    canvas.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_PageUp, Qt.NoModifier))
    assert canvas.index == 4
    canvas.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Home, Qt.NoModifier))
    assert canvas.index == 0


def test_health_page_skips_non_autoscan_ports(monkeypatch, tmp_path: Path) -> None:
    _app()
    exe = tmp_path / "longshot.exe"
    exe.write_bytes(b"MZ")
    store = _store(monkeypatch, tmp_path, [])
    page = HealthPage(store)
    page.set_emulators(
        [Emulator(key="longshot", name="Longshot", executable=str(exe), system="Ports", system_key="ports", found=True)]
    )
    page.refresh()
    labels = [lbl.text() for lbl in page.findChildren(QLabel)]
    assert any("Todo en orden" in text for text in labels)


def test_main_window_respects_locked_emulator_and_closes_cleanly(monkeypatch, tmp_path: Path) -> None:
    import umbral.paths as paths_mod
    import umbral.ui.main_window as mw_mod

    monkeypatch.setattr(store_module, "library_file", lambda: tmp_path / "library.json")
    monkeypatch.setattr(store_module, "settings_file", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(paths_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(mw_mod, "data_dir", lambda: tmp_path)

    _app()
    win = mw_mod.MainWindow()
    # Prevent deferred bootstrap timers from firing network/detection threads in test
    win.store.settings["update_last_check"] = "2099-01-01T00:00:00+00:00"
    emu1 = tmp_path / "snes9x.exe"
    emu2 = tmp_path / "ares.exe"
    emu1.write_bytes(b"MZ")
    emu2.write_bytes(b"MZ")
    win.emulators = [
        Emulator(key="snes9x", name="Snes9x", executable=str(emu1), system="SNES", system_key="snes", found=True),
        Emulator(key="ares", name="Ares", executable=str(emu2), system="Multi", system_key="multi", found=True),
    ]
    game = Game(id="snes-test", title="SMW", system="SNES", system_key="snes", rom_path=str(tmp_path / "smw.sfc"))
    assert len(win._emulator_candidates(game)) == 1
    game.emulator_locked = True
    assert win._emulator_candidates(game) == []
    win.close()
    _app().processEvents()
