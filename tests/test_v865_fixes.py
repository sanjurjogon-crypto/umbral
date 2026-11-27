from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QLineEdit

from umbral import paths as paths_mod
from umbral.covers import _candidate_titles, _is_strict_title_match
from umbral.models import Game
from umbral.store import Store
from umbral.ui.backdrop_dialog import BackdropPickerDialog
from umbral.ui.dialogs import AddGameDialog
from umbral.ui.pages import SettingsPage
from umbral.ui.shelf import ShelfCanvas, _apply_frosted_floor
from umbral.ui.widgets import StartupOverlay


def _app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    inst = QApplication.instance()
    return inst if isinstance(inst, QApplication) else QApplication([])


def test_wheel_does_not_step_and_drag_pans_shelf() -> None:
    _app()
    canvas = ShelfCanvas()
    canvas.resize(1200, 720)
    games = [
        Game(id=f"g{i}", title=f"Game {i}", system="PC", system_key="pc")
        for i in range(4)
    ]
    canvas.set_games(games)
    assert canvas.index == 0

    wheel_down = QWheelEvent(
        QPointF(600, 360),
        QPointF(600, 360),
        QPoint(0, -120),
        QPoint(0, -120),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.NoScrollPhase,
        False,
    )
    canvas.wheelEvent(wheel_down)
    assert canvas.index == 0

    # Left drag horizontally pans to next game without flipping
    press = QMouseEvent(
        QMouseEvent.MouseButtonPress,
        QPointF(600, 360),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(420, 360),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    release = QMouseEvent(
        QMouseEvent.MouseButtonRelease,
        QPointF(420, 360),
        Qt.LeftButton,
        Qt.NoButton,
        Qt.NoModifier,
    )
    canvas.mousePressEvent(press)
    canvas.mouseMoveEvent(move)
    canvas.mouseReleaseEvent(release)
    assert canvas.index == 1
    assert canvas.is_flipped() is False
    canvas.deleteLater()


def test_right_drag_3d_inspect_and_context_suppression() -> None:
    _app()
    canvas = ShelfCanvas()
    canvas.resize(1200, 720)
    canvas.set_games([Game(id="g1", title="Zelda", system="N64", system_key="n64")])
    canvas.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_F, Qt.NoModifier))
    assert canvas.is_back_zoomed() is True
    assert canvas.is_flipped() is False

    r_press = QMouseEvent(
        QMouseEvent.MouseButtonPress,
        QPointF(600, 360),
        Qt.RightButton,
        Qt.RightButton,
        Qt.NoModifier,
    )
    r_move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(640, 390),
        Qt.RightButton,
        Qt.RightButton,
        Qt.NoModifier,
    )
    r_rel = QMouseEvent(
        QMouseEvent.MouseButtonRelease,
        QPointF(640, 390),
        Qt.RightButton,
        Qt.NoButton,
        Qt.NoModifier,
    )
    canvas.mousePressEvent(r_press)
    canvas.mouseMoveEvent(r_move)
    assert canvas._inspect_yaw != 0.0
    assert canvas._inspect_pitch != 0.0
    canvas.mouseReleaseEvent(r_rel)
    assert canvas._suppress_context_menu is True
    canvas.deleteLater()


def test_frosted_floor_blur_multiplier() -> None:
    import numpy as np

    arr = np.zeros((100, 100, 3), dtype=np.float32)
    arr[60:, ::2, :] = 255.0
    out0 = _apply_frosted_floor(arr, floor_y=50.0, blur=0)
    out10 = _apply_frosted_floor(arr, floor_y=50.0, blur=10)
    assert not np.array_equal(out0[60:], out10[60:])


def test_strict_cover_matching_and_emulator_titles() -> None:
    assert _is_strict_title_match("Doom", "Doom") is True
    assert _is_strict_title_match("Doom", "Kingdom Hearts") is False
    assert _is_strict_title_match("60 Seconds! Reatomized", "60 Seconds! Reatomized") is True
    assert _is_strict_title_match("Mario", "Mario & Sonic at the Olympic Games") is False

    emu_game = Game(
        id="ps3-demon",
        title="Demon's Souls",
        system="PlayStation 3",
        system_key="ps3",
        executable="C:/Emulators/rpcs3.exe",
        rom_path="",
        emulator="RPCS3",
    )
    titles = _candidate_titles(emu_game)
    assert "rpcs3" not in [t.lower() for t in titles]
    assert "Demon's Souls" in titles


def test_dialogs_and_appearance_ui(monkeypatch, tmp_path: Path) -> None:
    app = _app()
    monkeypatch.setattr(paths_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr("umbral.ui.backdrop_dialog.search_backdrops", lambda *a, **kw: [])
    store = Store()
    page = SettingsPage(store)
    page.set_section("appearance")
    page.refresh()
    assert "Color de acento" not in " ".join(
        lbl.text() for lbl in page.findChildren(type(page.body.itemAt(0).widget()))
    )
    page.deleteLater()

    dlg = AddGameDialog()
    collapsed_h = dlg.sizeHint().height()
    dlg.advanced_button.setChecked(True)
    expanded_h = dlg.height()
    dlg.advanced_button.setChecked(False)
    recollapsed_h = dlg.height()
    assert expanded_h > collapsed_h
    assert recollapsed_h <= collapsed_h + 20
    dlg.deleteLater()

    bp = BackdropPickerDialog(Game(id="g1", title="Portal", system="PC", system_key="pc"))
    assert bp.findChildren(QLineEdit) == []
    app.processEvents()
    bp.reject()
    bp.deleteLater()
    app.processEvents()


def test_data_dir_defaults_to_downloads_umbral(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("UMBRAL_DATA_DIR", raising=False)
    monkeypatch.setattr(paths_mod, "downloads_dir", lambda: tmp_path / "Downloads")
    monkeypatch.setattr(paths_mod, "_legacy_data_dir", lambda: tmp_path / "AppData" / "Umbral")
    monkeypatch.setattr(paths_mod, "_MIGRATED", False)
    result = paths_mod.data_dir()
    assert result == tmp_path / "Downloads" / "Umbral"
    assert result.is_dir()


def test_startup_overlay_no_crash_and_miter() -> None:
    from PySide6.QtWidgets import QWidget

    app = _app()
    host = QWidget()
    host.resize(800, 600)
    overlay = StartupOverlay(host)
    overlay._elapsed_ms = 1700
    overlay.repaint()
    app.processEvents()
    host.deleteLater()


def test_v866_home_library_synopsis_and_backdrop_fixes(monkeypatch, tmp_path: Path) -> None:
    from datetime import datetime, timedelta, timezone
    from umbral.backdrops import game_backdrop
    from umbral.synopsis import _looks_spanish
    from umbral.ui.pages import HomePage, LibraryPage, _added_within_days

    _app()
    monkeypatch.setattr(paths_mod, "data_dir", lambda: tmp_path)

    # 3-day recent filter
    recent_g = Game(
        id="r1",
        title="Recent",
        system="PC",
        system_key="pc",
        added_at=datetime.now(timezone.utc).isoformat(),
    )
    old_g = Game(
        id="r2",
        title="Old",
        system="PC",
        system_key="pc",
        added_at=(datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
    )
    assert _added_within_days(recent_g, 3) is True
    assert _added_within_days(old_g, 3) is False

    # English with accented loanword should not be treated as Spanish
    assert _looks_spanish("Catch Pokémon across the region in this classic RPG.") is False
    assert _looks_spanish("Un juego de rol clásico en el que exploras la región.") is True

    # Backdrop fallback across migrated data_dir
    bd_dir = tmp_path / "backdrops"
    bd_dir.mkdir(parents=True, exist_ok=True)
    bd_file = bd_dir / "hero.jpg"
    bd_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 400)
    g_bd = Game(
        id="gbd",
        title="Hero",
        system="PC",
        system_key="pc",
        backdrop="C:/old/AppData/Umbral/backdrops/hero.jpg",
    )
    assert game_backdrop(g_bd) == bd_file

    # HomePage includes featured in console lists, "Todos los juegos" at bottom, and Library empty filter clears canvas
    store = Store()
    store.games = [recent_g, old_g]
    home = HomePage(store)
    home.refresh()
    home.deleteLater()

    lib = LibraryPage(store)
    lib.resize(1200, 720)
    lib.refresh()
    assert len(lib.canvas.items) == 2
    lib.set_filter("n64")
    assert len(lib.canvas.items) == 0
    assert lib._empty.isHidden() is False
    lib.deleteLater()
