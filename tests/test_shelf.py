from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication

from umbral.models import Game
from umbral.ui.shelf import ShelfCanvas, _dominant_color, case_profile


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_case_profile_differentiates_systems_and_stores() -> None:
    sw2 = case_profile(Game(id="sw2", title="Zelda", system="Switch 2", system_key="switch2"))
    g3ds = case_profile(Game(id="3ds", title="ALBW", system="3DS", system_key="3ds"))
    ps3 = case_profile(Game(id="ps3", title="Demon's Souls", system="PS3", system_key="ps3"))
    steam = case_profile(Game(id="st", title="Hades", system="Steam", system_key="steam", source="steam"))

    assert sw2.w_scale < steam.w_scale
    assert sw2.h_scale > g3ds.h_scale
    assert sw2.spine_color != g3ds.spine_color
    assert ps3.band_label == "PLAYSTATION 3"
    assert steam.band_label == "STEAM"


def test_dominant_color_extracts_saturated_cover_tone(tmp_path: Path) -> None:
    _app()
    from PySide6.QtGui import QPixmap

    img = QImage(40, 40, QImage.Format_ARGB32)
    img.fill(QColor(25, 130, 230))
    pixmap = QPixmap.fromImage(img)
    dominant = _dominant_color(pixmap, QColor("#d4af37"))
    assert dominant.blue() > dominant.red()

    fallback = QColor("#d4af37")
    assert _dominant_color(None, fallback) == fallback


def test_shelf_canvas_renders_mixed_cases_tilt_and_badges(tmp_path: Path) -> None:
    app = _app()
    cover = tmp_path / "cover.png"
    img = QImage(180, 240, QImage.Format_ARGB32)
    img.fill(QColor(180, 48, 38))
    img.save(str(cover))

    games = [
        Game(
            id="g1",
            title="Zelda Tears",
            system="Switch 2",
            system_key="switch2",
            emulator="Fritchii",
            cover=str(cover),
            favorite=True,
            progress="finished",
        ),
        Game(
            id="g2",
            title="A Link Between Worlds",
            system="3DS",
            system_key="3ds",
            emulator="Azahar",
            cover=str(cover),
        ),
        Game(
            id="g3",
            title="Dark Souls",
            system="Steam",
            system_key="steam",
            source="steam",
        ),
    ]
    canvas = ShelfCanvas()
    canvas.resize(1100, 620)
    canvas.set_games(games)
    canvas.show()
    app.processEvents()

    # Hover centered box on right-top corner should set tilt target
    rect = canvas._case_rect(
        canvas.items[0],
        canvas._slot_geometry(0, canvas._layout()[4], canvas._layout()[2]),
        canvas._layout()[0],
        canvas._layout()[1],
        canvas._layout()[2],
        canvas._layout()[3],
    )
    move = QMouseEvent(
        QEvent.MouseMove,
        QPointF(rect.right() - 12, rect.top() + 12),
        QPointF(rect.right() - 12, rect.top() + 12),
        Qt.NoButton,
        Qt.NoButton,
        Qt.NoModifier,
    )
    canvas.mouseMoveEvent(move)
    assert canvas._tilt_target_x > 0.0
    assert canvas._tilt_target_y < 0.0

    canvas.leaveEvent(QEvent(QEvent.Leave))
    assert canvas._tilt_target_x == 0.0
    assert canvas._tilt_target_y == 0.0

    rendered = canvas.grab()
    assert not rendered.isNull()
    # Complete 3D front & alpha-faded reflection caches populated for visible cases (including neighbors)
    assert canvas.items[0].front_cache is not None
    assert canvas.items[1].front_cache is not None
    assert canvas.items[2].front_cache is not None
    assert canvas.items[0].refl_cache is not None
    assert canvas.items[1].refl_cache is not None
    assert canvas.items[2].refl_cache is not None

    # Halo toggle & rotated-rectangle perspective check
    canvas.set_halo_enabled(False)
    assert canvas._halo_enabled is False
    assert not canvas.grab().isNull()

    from umbral.ui.shelf import _perspective_quad, render_debanded_backdrop
    quad_left = _perspective_quad(200.0, 300.0, 0.85, -1.0)
    # Left & right vertical edges stay truly vertical (not trapezoidally pinched)
    assert abs(quad_left[0].x() - quad_left[3].x()) < 0.01
    assert abs(quad_left[1].x() - quad_left[2].x()) < 0.01
    # Continuous turn interpolation has zero discontinuity across center (turn = -0.01 vs +0.01)
    q_neg = _perspective_quad(200.0, 300.0, 0.12, -0.01)
    q_pos = _perspective_quad(200.0, 300.0, 0.12, 0.01)
    for p1, p2 in zip(q_neg, q_pos):
        assert abs(p1.y() - p2.y()) < 1.0

    # Sharp cover backdrop preserves high-frequency edge contrast (not gaussian-blurred away)
    sharp_src = tmp_path / "sharp_grid.png"
    grid_img = QImage(400, 400, QImage.Format_RGB32)
    for y in range(400):
        for x in range(400):
            grid_img.setPixelColor(x, y, QColor(240, 220, 120) if (x // 8) % 2 == 0 else QColor(20, 20, 30))
    grid_img.save(str(sharp_src))
    bg = render_debanded_backdrop(
        640, 360, 320.0, 180.0, 222.0, 300.0, str(sharp_src), None, QColor("#d4af37"), True
    )
    assert bg.size().width() == 640 and bg.size().height() == 360
    sample = bg.toImage()
    # Adjacent stripe regions should preserve clear contrast difference
    vals = [sample.pixelColor(x, 180).red() for x in range(280, 360, 4)]
    assert max(vals) - min(vals) > 25

    canvas.step(1)
    assert canvas.index == 1
    assert canvas._backdrop_mix == 0.0 or canvas._bg_anim.state()
    canvas.close()
    app.processEvents()
