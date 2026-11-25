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

    page.set_query("")
    page.resize(1200, 760)
    page.refresh(reset=True)
    # Alphabetical order selects "Hades" (PC/Standalone) at index 0, then "Zelda" (Dolphin) at index 1
    assert page.info_emu_icon.isHidden()
    page.canvas.step(1)
    assert not page.info_emu_icon.isHidden()


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
    win.deleteLater()
    _app().processEvents()


def test_game_detail_dialog_buttons_do_not_overlap() -> None:
    from PySide6.QtWidgets import QPushButton

    from umbral.ui.dialogs import GameDetailDialog
    from umbral.ui.style import active
    from umbral.ui.theme import qss
    from umbral.ui.theme_extra import extra_qss

    app = _app()
    style = active()
    app.setStyleSheet(qss(style.accent, style.key) + extra_qss(style))
    game = Game(
        id="ports-oot-longshot",
        title="The Legend of Zelda: Ocarina of Time",
        system="Ports",
        system_key="ports",
        subtitle="Ports · Port nativo (Longshot)",
        year=2026,
        genre="Aventura",
        emulator="Longshot",
        description="El remake de Ocarina of Time reconstruido para PC.",
    )
    dialog = GameDetailDialog(game)
    dialog.show()
    app.processEvents()

    buttons = dialog.findChildren(QPushButton)
    assert len(buttons) == 8
    for first_index, first in enumerate(buttons):
        rect_a = first.geometry()
        assert rect_a.width() >= first.minimumWidth()
        for second in buttons[first_index + 1 :]:
            assert not rect_a.intersects(second.geometry())

    dialog.favorite_button.click()
    dialog.progress_button.click()
    app.processEvents()
    for first_index, first in enumerate(buttons):
        rect_a = first.geometry()
        for second in buttons[first_index + 1 :]:
            assert not rect_a.intersects(second.geometry())

    dialog.close()
    app.processEvents()


def test_library_grid_view_and_hide_demos(monkeypatch, tmp_path: Path) -> None:
    _app()
    games = [
        Game(id="g1", title="Hades", system="Steam", system_key="steam", source="steam"),
        Game(id="g2", title="Cardsharp Demo", system="Steam", system_key="steam", source="steam"),
        Game(id="g3", title="Dumbfire Playtest", system="Steam", system_key="steam", source="steam"),
    ]
    store = _store(monkeypatch, tmp_path, games)
    page = LibraryPage(store)
    page.resize(1100, 720)

    assert page.filters_button.objectName() == "filterBtn"
    page.hide_demos_action.setChecked(True)
    assert [g.id for g in page._visible_games()] == ["g1"]
    assert store.settings["hide_demos"] is True

    page._set_view_mode("grid")
    page.show()
    _app().processEvents()
    assert store.settings["library_view"] == "grid"
    assert page.grid_scroll.isVisibleTo(page)
    assert not page.canvas.isVisibleTo(page)
    assert page.grid_layout.count() == 1
    assert page.grid_layout.itemAt(0).widget().isVisibleTo(page)

    page._set_view_mode("shelf")
    assert store.settings["library_view"] == "shelf"
    assert page.canvas.isVisibleTo(page)
    assert not page.grid_scroll.isVisibleTo(page)


def test_health_page_shows_stores_duplicates_and_add_folder(monkeypatch, tmp_path: Path) -> None:
    import umbral.ui.pages as pages_mod

    _app()
    monkeypatch.setattr(
        pages_mod,
        "store_statuses",
        lambda: [("steam", "Steam", True), ("epic", "Epic Games", False), ("gog", "GOG", False)],
    )
    exe = tmp_path / "rpcs3.exe"
    exe.write_bytes(b"MZ")
    rom1 = tmp_path / "a" / "oot.nup"
    rom2 = tmp_path / "b" / "oot.nup"
    rom1.parent.mkdir()
    rom2.parent.mkdir()
    rom1.write_bytes(b"ROM")
    rom2.write_bytes(b"ROM")

    games = [
        Game(id="steam-1", title="Dark Souls", system="Steam", system_key="steam", source="steam", executable=str(exe)),
        Game(id="dup-1", title="Ocarina of Time", system="Switch 2", system_key="switch2", emulator="Fritchii", executable=str(exe), rom_path=str(rom1)),
        Game(id="dup-2", title="Ocarina of Time", system="Switch 2", system_key="switch2", emulator="Fritchii", executable=str(exe), rom_path=str(rom2)),
    ]
    store = _store(monkeypatch, tmp_path, games)
    page = HealthPage(store)
    page.set_emulators(
        [Emulator(key="rpcs3", name="RPCS3", executable=str(exe), system="PS3", system_key="ps3", found=True)]
    )
    page.refresh()

    texts = [lbl.text() for lbl in page.findChildren(QLabel)]
    assert any("Copias duplicadas: Ocarina of Time" in text for text in texts)
    assert any("Steam" == text for text in texts)
    assert any("Detectada · 1 juego" in text for text in texts)


def test_settings_page_lists_hidden_games_and_emits_restore(monkeypatch, tmp_path: Path) -> None:
    from PySide6.QtWidgets import QPushButton

    from umbral.ui.pages import SettingsPage

    _app()
    store = _store(monkeypatch, tmp_path, [])
    store.settings["hidden_games"] = ["pc-boxshelf-1"]
    store.settings["hidden_paths"] = ["c:/games/boxshelf.exe"]
    page = SettingsPage(store)
    page.refresh()

    restored_games: list[str] = []
    restored_paths: list[str] = []
    page.unhide_game_requested.connect(restored_games.append)
    page.unhide_path_requested.connect(restored_paths.append)

    restore_buttons = [btn for btn in page.findChildren(QPushButton) if btn.text() == "Restaurar"]
    assert len(restore_buttons) == 2
    restore_buttons[0].click()
    restore_buttons[1].click()
    assert restored_games == ["pc-boxshelf-1"]
    assert restored_paths == ["c:/games/boxshelf.exe"]

    # Estantería 3D halo toggle persists & emits halo_changed
    halo_events: list[bool] = []
    page.halo_changed.connect(halo_events.append)
    assert page.halo_check.isChecked() is True
    page.halo_check.setChecked(False)
    assert store.settings["shelf_halo"] is False
    assert halo_events == [False]


def test_main_window_chrome_insets_and_sidebar_indicators(monkeypatch, tmp_path: Path) -> None:
    import umbral.paths as paths_mod
    import umbral.ui.main_window as mw_mod

    monkeypatch.setattr(store_module, "library_file", lambda: tmp_path / "library.json")
    monkeypatch.setattr(store_module, "settings_file", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(paths_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(mw_mod, "data_dir", lambda: tmp_path)

    app = _app()
    win = mw_mod.MainWindow()
    win.store.settings["update_last_check"] = "2099-01-01T00:00:00+00:00"
    win.store.games = [
        Game(id="g1", title="Zelda", system="Ports", system_key="ports", favorite=True),
        Game(id="g2", title="Hades", system="Steam", system_key="steam", source="steam"),
    ]
    win.resize(1280, 760)
    win.show()
    app.processEvents()

    assert win.library._inset_left == win._sidebar_width
    assert win.library._inset_top == win._topbar_height
    assert win.sidebar.width() == win._sidebar_width
    assert win.topbar.x() == win._sidebar_width

    win._navigate("home")
    app.processEvents()
    assert win.stack.currentWidget() is win.home

    win._navigate("library")
    app.processEvents()
    assert win.stack.currentWidget() is win.library

    first_btn = win._system_buttons.get("")
    win._filter_system("steam")
    app.processEvents()
    # System filter button instance reused cleanly across transitions (no full teardown)
    assert win._system_buttons.get("") is first_btn
    assert win.library.current_filter() == "steam"

    win.close()
    win.deleteLater()
    app.processEvents()


def test_home_hero_banner_and_card_row_redesign(monkeypatch, tmp_path: Path) -> None:
    from PySide6.QtWidgets import QLabel

    from umbral.ui.pages import HomePage
    from umbral.ui.widgets import CardRow

    app = _app()
    store = _store(
        monkeypatch,
        tmp_path,
        [
            Game(id="g1", title="Zelda", system="Switch", system_key="switch", favorite=True, last_played="2026-11-24T12:00:00"),
            Game(id="g2", title="Hades", system="Steam", system_key="steam", source="steam", playtime_seconds=7200),
        ],
    )
    home = HomePage(store)
    home.refresh()
    assert home.hero.height() <= 260
    rows = home.findChildren(CardRow)
    assert len(rows) >= 1
    assert any(lbl.text() == "1" for lbl in rows[0].findChildren(QLabel))
    home.close()
    home.deleteLater()
    app.processEvents()


def test_startup_overlay_renders_all_phases() -> None:
    from PySide6.QtWidgets import QWidget

    from umbral.ui.widgets import StartupOverlay

    app = _app()
    host = QWidget()
    host.resize(1280, 720)
    overlay = StartupOverlay(host)
    overlay.setGeometry(0, 0, 1280, 720)
    overlay.start()

    for elapsed in (0, 1000, 1320, 1850, 2300):
        overlay._elapsed_ms = elapsed
        overlay.repaint()
        app.processEvents()

    overlay._elapsed_ms = overlay._total_ms
    overlay._tick()
    assert not overlay.isVisible()
    host.close()
    host.deleteLater()
    app.processEvents()


def test_styles_catalog_and_appearance_tab_switch(monkeypatch, tmp_path: Path) -> None:
    from umbral.ui.pages import SettingsPage
    from umbral.ui.style import STYLES, set_active, style_for
    from umbral.ui.widgets import StylePreview

    app = _app()
    assert [s.key for s in STYLES] == ["umbral", "obsidian", "neon", "forest"]
    assert style_for("neon").key == "neon"
    set_active("umbral")

    store = _store(monkeypatch, tmp_path, [])
    page = SettingsPage(store)
    page.refresh()
    page.set_section("appearance")
    cards = page.findChildren(StylePreview)
    assert len(cards) == 4
    picked: list[str] = []
    page.style_changed.connect(picked.append)
    cards[1].clicked.emit("obsidian")
    assert picked == ["obsidian"]
    page.deleteLater()
    app.processEvents()


def test_collapsible_sidebar_and_right_click_does_not_launch(monkeypatch, tmp_path: Path) -> None:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest

    import umbral.paths as paths_mod
    import umbral.ui.main_window as mw_mod
    from umbral.ui.widgets import GameCard

    monkeypatch.setattr(store_module, "library_file", lambda: tmp_path / "library.json")
    monkeypatch.setattr(store_module, "settings_file", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(paths_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(mw_mod, "data_dir", lambda: tmp_path)

    app = _app()
    win = mw_mod.MainWindow()
    win.store.settings["update_last_check"] = "2099-01-01T00:00:00+00:00"
    game = Game(id="g1", title="Zelda", system="Ports", system_key="ports")
    win.store.games = [game]
    win._refresh_all()
    win.resize(1280, 760)
    win.show()
    app.processEvents()

    assert not hasattr(win.library, "details_button")
    assert win._sidebar_width == 238
    assert win.sidebar_toggle.text() == "«"
    win.sidebar_toggle.click()
    assert win._sidebar_width == 0
    assert win.sidebar_toggle.text() == "»"
    assert not win.sidebar.isVisible()
    win.sidebar_toggle.click()
    assert win._sidebar_width == 238
    assert win.sidebar_toggle.text() == "«"
    assert win.sidebar.isVisible()

    from umbral.ui.style import STYLES

    assert all(style.radius == 8 for style in STYLES)

    # Right-click on centered ShelfCanvas item must NOT emit activated
    activated: list[Game] = []
    win.library.canvas.activated.connect(activated.append)
    cx, cy, _w, _h, _g = win.library.canvas._layout()
    evt = QMouseEvent(
        QMouseEvent.MouseButtonPress,
        QPointF(cx, cy),
        QPointF(cx, cy),
        Qt.RightButton,
        Qt.RightButton,
        Qt.NoModifier,
    )
    win.library.canvas.mousePressEvent(evt)
    assert activated == []

    # Left-click on GameCard emits play_requested directly
    card = GameCard(game)
    played: list[Game] = []
    card.play_requested.connect(played.append)
    QTest.mouseClick(card, Qt.LeftButton, pos=card.rect().center())
    assert played == [game]

    card.deleteLater()
    win.close()
    win.deleteLater()
    app.processEvents()


def test_settings_page_uses_submenus_and_empty_state_does_not_clip(monkeypatch, tmp_path: Path) -> None:
    from umbral.ui.pages import SettingsPage
    from umbral.ui.widgets import EmptyState

    app = _app()
    store = _store(monkeypatch, tmp_path, [])
    page = SettingsPage(store)
    page.refresh()

    assert set(page._tab_buttons.keys()) == {"emulators", "library", "appearance", "maintenance"}
    assert page._stack is not None
    page.set_section("appearance")
    assert page._active_tab == "appearance"
    assert page._stack.currentIndex() == page._tab_indices["appearance"]

    empty = EmptyState(
        "Todavía no hay favoritos",
        "Abre la ficha de un juego y pulsa la estrella para guardarlo aquí. "
        "Puedes añadir tantos juegos como quieras desde cualquier sistema.",
        "",
    )
    empty.set_text(
        "Todavía no hay favoritos",
        "Abre la ficha de un juego y pulsa la estrella para guardarlo aquí. "
        "Puedes añadir tantos juegos como quieras desde cualquier sistema.",
        "",
    )
    empty.resize(800, 500)
    empty.show()
    app.processEvents()
    assert empty.description_label.height() >= empty.description_label.fontMetrics().lineSpacing() * 2
    empty.close()
    empty.deleteLater()
    page.deleteLater()
    app.processEvents()


def test_library_shelf_title_expands_for_long_multiline_titles(monkeypatch, tmp_path: Path) -> None:
    from umbral.ui.pages import LibraryPage

    app = _app()
    long_title = "IRON NEST: HEAVY TURRET SIMULATOR DELUXE EDITION"
    store = _store(
        monkeypatch,
        tmp_path,
        [Game(id="g1", title=long_title, system="Steam", system_key="steam", source="steam")],
    )
    lib = LibraryPage(store)
    lib.resize(700, 720)
    lib.show()
    lib.refresh()
    app.processEvents()

    assert lib.info_title.height() >= lib.info_title.fontMetrics().lineSpacing() * 2
    center_x, center_y, cover_w, cover_h, _gap = lib.canvas._layout()
    assert center_y + cover_h / 2.0 <= lib.bottom.y() + 2

    # Switching to a shorter title must shrink info_title back down
    two_line_h = lib.info_title.height()
    lib._on_selection(Game(id="g2", title="Hades", system="Steam", system_key="steam", source="steam"))
    app.processEvents()
    one_line_h = lib.info_title.height()
    assert one_line_h < two_line_h
    lib.close()
    lib.deleteLater()
    app.processEvents()


def test_sidebar_buttons_have_no_focus_and_arrows_stay_in_shelf(monkeypatch, tmp_path: Path) -> None:
    import umbral.paths as paths_mod
    import umbral.ui.main_window as mw_mod

    monkeypatch.setattr(store_module, "library_file", lambda: tmp_path / "library.json")
    monkeypatch.setattr(store_module, "settings_file", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(paths_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(mw_mod, "data_dir", lambda: tmp_path)

    app = _app()
    win = mw_mod.MainWindow()
    win.store.settings["update_last_check"] = "2099-01-01T00:00:00+00:00"
    win.store.games = [
        Game(id="g1", title="Zelda", system="Ports", system_key="ports"),
        Game(id="g2", title="Hades", system="Steam", system_key="steam", source="steam"),
    ]
    win._rebuild_systems()
    for btn in (*win.nav_buttons.values(), win.update_button, *win._system_buttons.values()):
        assert btn.focusPolicy() == Qt.NoFocus

    win.close()
    win.deleteLater()
    app.processEvents()


def test_home_hero_banner_and_card_row_redesign(monkeypatch, tmp_path: Path) -> None:
    from PySide6.QtWidgets import QLabel

    from umbral.ui.pages import HomePage
    from umbral.ui.widgets import CardRow

    app = _app()
    store = _store(
        monkeypatch,
        tmp_path,
        [
            Game(id="g1", title="Zelda", system="Switch", system_key="switch", favorite=True, last_played="2026-11-24T12:00:00"),
            Game(id="g2", title="Hades", system="Steam", system_key="steam", source="steam", playtime_seconds=7200),
        ],
    )
    home = HomePage(store)
    home.refresh()
    assert home.hero.height() <= 260
    rows = home.findChildren(CardRow)
    assert len(rows) >= 1
    assert any(lbl.text() == "1" for lbl in rows[0].findChildren(QLabel))
    home.close()
    home.deleteLater()
    app.processEvents()


def test_startup_overlay_renders_all_phases() -> None:
    from PySide6.QtWidgets import QWidget

    from umbral.ui.widgets import StartupOverlay

    app = _app()
    host = QWidget()
    host.resize(1280, 720)
    overlay = StartupOverlay(host)
    overlay.setGeometry(0, 0, 1280, 720)
    overlay.start()

    for elapsed in (0, 1000, 1320, 1850, 2300):
        overlay._elapsed_ms = elapsed
        overlay.repaint()
        app.processEvents()

    overlay._elapsed_ms = overlay._total_ms
    overlay._tick()
    assert not overlay.isVisible()
    host.close()
    host.deleteLater()
    app.processEvents()


def test_styles_catalog_and_appearance_tab_switch(monkeypatch, tmp_path: Path) -> None:
    from umbral.ui.pages import SettingsPage
    from umbral.ui.style import STYLES, set_active, style_for
    from umbral.ui.widgets import StylePreview

    app = _app()
    assert [s.key for s in STYLES] == ["umbral", "obsidian", "neon", "forest"]
    assert style_for("neon").key == "neon"
    set_active("umbral")

    store = _store(monkeypatch, tmp_path, [])
    page = SettingsPage(store)
    page.refresh()
    page.set_section("appearance")
    cards = page.findChildren(StylePreview)
    assert len(cards) == 4
    picked: list[str] = []
    page.style_changed.connect(picked.append)
    cards[1].clicked.emit("obsidian")
    assert picked == ["obsidian"]
    page.deleteLater()
    app.processEvents()


def test_collapsible_sidebar_and_right_click_does_not_launch(monkeypatch, tmp_path: Path) -> None:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest

    import umbral.paths as paths_mod
    import umbral.ui.main_window as mw_mod
    from umbral.ui.widgets import GameCard

    monkeypatch.setattr(store_module, "library_file", lambda: tmp_path / "library.json")
    monkeypatch.setattr(store_module, "settings_file", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(paths_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(mw_mod, "data_dir", lambda: tmp_path)

    app = _app()
    win = mw_mod.MainWindow()
    win.store.settings["update_last_check"] = "2099-01-01T00:00:00+00:00"
    game = Game(id="g1", title="Zelda", system="Ports", system_key="ports")
    win.store.games = [game]
    win._refresh_all()
    win.resize(1280, 760)
    win.show()
    app.processEvents()

    assert not hasattr(win.library, "details_button")
    assert win._sidebar_width == 238
    assert win.sidebar_toggle.text() == "«"
    win.sidebar_toggle.click()
    assert win._sidebar_width == 0
    assert win.sidebar_toggle.text() == "»"
    assert not win.sidebar.isVisible()
    win.sidebar_toggle.click()
    assert win._sidebar_width == 238
    assert win.sidebar_toggle.text() == "«"
    assert win.sidebar.isVisible()

    from umbral.ui.style import STYLES

    assert all(style.radius == 8 for style in STYLES)

    # Right-click on centered ShelfCanvas item must NOT emit activated
    activated: list[Game] = []
    win.library.canvas.activated.connect(activated.append)
    cx, cy, _w, _h, _g = win.library.canvas._layout()
    evt = QMouseEvent(
        QMouseEvent.MouseButtonPress,
        QPointF(cx, cy),
        QPointF(cx, cy),
        Qt.RightButton,
        Qt.RightButton,
        Qt.NoModifier,
    )
    win.library.canvas.mousePressEvent(evt)
    assert activated == []

    # Left-click on GameCard emits play_requested directly
    card = GameCard(game)
    played: list[Game] = []
    card.play_requested.connect(played.append)
    QTest.mouseClick(card, Qt.LeftButton, pos=card.rect().center())
    assert played == [game]

    card.deleteLater()
    win.close()
    win.deleteLater()
    app.processEvents()


def test_custom_game_backdrop_renders_crisp_in_shelf(monkeypatch, tmp_path: Path) -> None:
    from PIL import Image
    from umbral.backdrops import BackdropOption, game_backdrop
    from umbral.ui.backdrop_dialog import BackdropPickerDialog
    from umbral.ui.shelf import ShelfCanvas

    app = _app()
    bg_file = tmp_path / "custom_bg.jpg"
    Image.new("RGB", (640, 360), (20, 120, 210)).save(bg_file)

    game = Game(id="bg1", title="Hollow Knight", system="PC", system_key="pc", backdrop=str(bg_file))
    assert game_backdrop(game) == bg_file

    canvas = ShelfCanvas()
    canvas.resize(800, 600)
    canvas.set_games([game])
    cx, cy, cw, ch, _gap = canvas._layout()
    pix = canvas._backdrop_for(canvas._current_item(), cx, cy, cw, ch)
    assert not pix.isNull()
    assert pix.width() == 800 and pix.height() == 600
    # Top half should preserve crisp blue color without blur/washout, bottom is darkened
    img = pix.toImage()
    top_pixel = img.pixelColor(400, 100)
    bot_pixel = img.pixelColor(400, 580)
    assert top_pixel.blue() > 180
    assert bot_pixel.blue() < top_pixel.blue()

    canvas.set_chrome_insets(238, 0)
    cx2, cy2, cw2, ch2, _ = canvas._layout()
    pix_sidebar = canvas._backdrop_for(canvas._current_item(), cx2, cy2, cw2, ch2)
    img2 = pix_sidebar.toImage()
    # Left strip mirrors image pixels so collapsing sidebar never exposes black gaps
    assert img2.pixelColor(100, 100).blue() > 80
    assert img2.pixelColor(520, 100).blue() > 180

    # Per-game backdrop settings (dim, blur, align) + bottom-right menu
    game.backdrop_dim = 0.55
    game.backdrop_blur = 6
    game.backdrop_align = "top"
    pix_dim = canvas._backdrop_for(canvas._current_item(), cx2, cy2, cw2, ch2)
    assert pix_dim.toImage().pixelColor(520, 100).blue() < img2.pixelColor(520, 100).blue()

    store = _store(monkeypatch, tmp_path, [game])
    page = LibraryPage(store)
    page.resize(900, 650)
    page.refresh()
    assert page.backdrop_button.objectName() == "filterBtn"
    assert page.title_box_frame.objectName() == "shelfTitleBox"
    page._populate_backdrop_menu()
    labels = [act.text() for act in page._backdrop_menu.actions() if act.text()]
    assert "Encuadre" in labels
    assert "Cambiar fondo..." in labels
    assert "Restaurar por defecto" in labels
    from PySide6.QtWidgets import QSlider
    assert len(page._backdrop_menu.findChildren(QSlider)) == 2

    monkeypatch.setattr(
        "umbral.ui.backdrop_dialog.search_backdrops",
        lambda q, game=None, max_results=12: [
            BackdropOption(url="https://example.com/a.jpg", thumb_url="https://example.com/t.jpg", title=q, source="IGDB")
        ],
    )
    monkeypatch.setattr("umbral.ui.backdrop_dialog.fetch_thumbnail", lambda _url: None)
    dlg = BackdropPickerDialog(game)
    dlg.close()
    dlg.deleteLater()
    canvas.deleteLater()
    app.processEvents()
