from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import QWidget

from ..covers import game_cover
from ..icons import exe_pixmap
from ..models import Game
from ..profiles import PROFILES
from .scenes import paint_scene
from .style import active as active_style

CASE_W = 222.0
CASE_H = 300.0
CASE_DEPTH = 26.0
TITLE_BAND_RATIO = 0.112

TRI = "#8b9a72"
SQUARE = "#b07a4a"
CROSS = "#8c99a6"
CIRCLE = "#a64036"
SELECT_GLOW = QColor(201, 164, 95, 130)

UI_FONT = "Cinzel"

EMULATOR_COLORS: dict[str, str] = {profile.key: profile.accent for profile in PROFILES}
EMULATOR_NAMES: dict[str, str] = {profile.key: profile.name for profile in PROFILES}
EMULATOR_BY_NAME: dict[str, str] = {
    profile.name.lower(): profile.key for profile in PROFILES
}

PC_BAND = "#17130d"
PC_BAND_LIGHT = "#2a2317"

CANVAS_BG = "#070604"
WASH_TOP = "#0c0a07"
WASH_MID = "#090705"
WASH_BOTTOM = "#050403"
HALO_MAIN = QColor(201, 164, 95, 34)
HALO_SOFT = QColor(140, 100, 50, 12)
SPINE_COLOR = QColor(201, 164, 95)
ACCENT_TEXT = "#e7d6ad"


def apply_style(style_key: str) -> None:
    global TRI, SQUARE, CROSS, CIRCLE, SELECT_GLOW, UI_FONT
    global PC_BAND, PC_BAND_LIGHT, CANVAS_BG, WASH_TOP, WASH_MID, WASH_BOTTOM
    global HALO_MAIN, HALO_SOFT, SPINE_COLOR, ACCENT_TEXT
    from .style import style_for

    style = style_for(style_key)
    UI_FONT = style.heading_font
    SELECT_GLOW = QColor(style.accent)
    SELECT_GLOW.setAlpha(130)
    TRI = style.success
    SQUARE = style.accent
    CROSS = style.muted
    CIRCLE = style.danger
    PC_BAND = _mix(QColor(style.surface_2), QColor(style.bg), 0.25).name()
    PC_BAND_LIGHT = _mix(QColor(style.surface_3), QColor(style.bg), 0.1).name()
    CANVAS_BG = style.canvas
    WASH_TOP = _mix(QColor(style.bg), QColor(style.surface_2), 0.35).name()
    WASH_MID = style.bg
    WASH_BOTTOM = _mix(QColor(style.bg), QColor("#000000"), 0.35).name()
    accent = QColor(style.accent)
    HALO_MAIN = QColor(accent)
    HALO_MAIN.setAlpha(34)
    HALO_SOFT = QColor(accent)
    HALO_SOFT.setAlpha(12)
    SPINE_COLOR = accent
    ACCENT_TEXT = style.accent_2


_ICON_CACHE: dict[str, Optional[QPixmap]] = {}


def _exe_badge(executable: str) -> Optional[QPixmap]:
    key = executable or ""
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    pixmap = exe_pixmap(key) if key else None
    if pixmap is None and key:
        pixmap = _launcher_badge(key)
    _ICON_CACHE[key] = pixmap
    return pixmap


def _launcher_badge(executable: str) -> Optional[QPixmap]:
    path = Path(executable)
    if path.name.lower() != "longshot.exe":
        return None
    local_env = os.environ.get("LOCALAPPDATA", "").strip()
    candidates = [
        path.parent / "LongshotLauncher.exe",
        path.parent.parent / "LongshotLauncher.exe",
    ]
    if local_env:
        candidates.insert(
            0, Path(local_env) / "Programs" / "LongshotLauncher" / "LongshotLauncher.exe"
        )
    for candidate in candidates:
        if candidate.is_file():
            return exe_pixmap(str(candidate))
    return None


def _emulator_key(game: Game) -> str:
    name = (game.emulator or "").strip().lower()
    if not name:
        return ""
    return EMULATOR_BY_NAME.get(name, "")


def _is_pc_case(game: Game) -> bool:
    return game.system_key == "pc" or (game.emulator or "").strip().lower() in {
        "standalone",
        "",
    }


def _band_text(game: Game) -> str:
    if _is_pc_case(game):
        return "PC"
    key = _emulator_key(game)
    if key and key in EMULATOR_NAMES:
        return EMULATOR_NAMES[key]
    return game.emulator or game.system or "PC"


def _band_color(game: Game) -> QColor:
    if _is_pc_case(game):
        return QColor(PC_BAND)
    key = _emulator_key(game)
    color = QColor(EMULATOR_COLORS.get(key, game.accent or "#E9B949"))
    if not color.isValid():
        color = QColor("#E9B949")
    return color


def _readable_on(color: QColor) -> QColor:
    luminance = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
    return QColor("#0c0e13") if luminance > 150 else QColor("#f5f7fb")


def _smooth(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def _perspective_quad(width: float, height: float, tilt: float, side: float) -> list[QPointF]:
    half_w = width / 2.0
    half_h = height / 2.0
    inset = half_w * 0.11 * tilt * (1.0 if side >= 0 else 1.0)
    top_inset = inset
    bottom_inset = inset * 0.18
    shift = side * half_w * 0.045 * tilt
    return [
        QPointF(-half_w + top_inset + shift * 0.4, -half_h + inset * 0.12),
        QPointF(half_w - top_inset * 0.35 + shift, -half_h - inset * 0.12),
        QPointF(half_w - bottom_inset + shift, half_h - inset * 0.05),
        QPointF(-half_w + bottom_inset * 0.35 + shift * 0.4, half_h + inset * 0.05),
    ]


def _quad_transform(source: list[QPointF], quad: list[QPointF]) -> QTransform:
    rows: list[list[float]] = []
    for point, unit in zip(quad, source):
        rows.append(
            [unit.x(), unit.y(), 1.0, 0.0, 0.0, 0.0, -point.x() * unit.x(), -point.x() * unit.y(), point.x()]
        )
        rows.append(
            [0.0, 0.0, 0.0, unit.x(), unit.y(), 1.0, -point.y() * unit.x(), -point.y() * unit.y(), point.y()]
        )

    size = 8
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(rows[r][col]))
        if pivot != col:
            rows[col], rows[pivot] = rows[pivot], rows[col]
        diagonal = rows[col][col]
        if abs(diagonal) < 1e-12:
            return QTransform()
        for col2 in range(col, size + 1):
            rows[col][col2] /= diagonal
        for row in range(size):
            if row == col:
                continue
            factor = rows[row][col]
            if factor == 0:
                continue
            for col2 in range(col, size + 1):
                rows[row][col2] -= factor * rows[col][col2]

    h11, h12, h13, h21, h22, h23, h31, h32 = (rows[i][size] for i in range(size))
    return QTransform(h11, h21, h31, h12, h22, h32, h13, h23, 1.0)


@dataclass
class ShelfItem:
    game: Game
    pixmap: Optional[QPixmap]


class ShelfCanvas(QWidget):
    activated = Signal(object)
    details_requested = Signal(object)
    selection_changed = Signal(object)
    context_requested = Signal(object, object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shelfCanvas")
        self.setMinimumHeight(360)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

        self.items: list[ShelfItem] = []
        self.index = 0
        self._float = 0.0
        self._target = 0.0
        self._hover_index = -1
        self._hover_lift = 0.0
        self._anim = QPropertyAnimation(self, b"position", self)
        self._anim.setDuration(520)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self._hover_anim = QPropertyAnimation(self, b"hover_lift", self)
        self._hover_anim.setDuration(220)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

    def get_float(self) -> float:
        return self._float

    def set_float(self, value: float) -> None:
        self._float = float(value)
        self.update()

    position = Property(float, get_float, set_float)

    def get_hover_lift(self) -> float:
        return self._hover_lift

    def set_hover_lift(self, value: float) -> None:
        self._hover_lift = float(value)
        self.update()

    hover_lift = Property(float, get_hover_lift, set_hover_lift)

    def set_games(self, games: list[Game]) -> None:
        previous = self.current_game()
        self.items = [ShelfItem(game, self._load(game)) for game in games]
        self.index = 0
        if previous is not None:
            for position, item in enumerate(self.items):
                if item.game.id == previous.id:
                    self.index = position
                    break
        self.index = max(0, min(self.index, len(self.items) - 1))
        self._float = float(self.index)
        self._target = self._float
        self._sync()
        self._emit_selection()

    def _load(self, game: Game) -> Optional[QPixmap]:
        path = game_cover(game)
        if path is None:
            return None
        pixmap = QPixmap(str(path))
        return None if pixmap.isNull() else pixmap

    def reset_position(self) -> None:
        self._anim.stop()
        self.index = 0
        self._float = 0.0
        self._target = 0.0
        self.update()

    def current_game(self) -> Optional[Game]:
        if not self.items:
            return None
        if 0 <= self.index < len(self.items):
            return self.items[self.index].game
        return None

    def _sync(self) -> None:
        self._anim.stop()
        target = float(self.index)
        self._anim.setStartValue(self._float)
        self._anim.setEndValue(target)
        self._anim.start()
        self.update()

    def _emit_selection(self) -> None:
        game = self.current_game()
        if game is not None:
            self.selection_changed.emit(game)
        self.update()

    def step(self, delta: int) -> None:
        if not self.items:
            return
        self.index = max(0, min(self.index + delta, len(self.items) - 1))
        self._sync()
        self._emit_selection()

    def moveEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().moveEvent(event)
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().resizeEvent(event)
        self.update()

    def wheelEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if not self.items:
            return
        delta = -1 if event.angleDelta().y() > 0 else 1
        self.step(delta)
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - API de Qt
        key = event.key()
        if key in (Qt.Key_Left, Qt.Key_A):
            self.step(-1)
            event.accept()
            return
        if key in (Qt.Key_Right, Qt.Key_D):
            self.step(1)
            event.accept()
            return
        if key == Qt.Key_Home and self.items:
            self.step(-self.index)
            event.accept()
            return
        if key == Qt.Key_End and self.items:
            self.step(len(self.items) - 1 - self.index)
            event.accept()
            return
        if key == Qt.Key_PageUp:
            self.step(-5)
            event.accept()
            return
        if key == Qt.Key_PageDown:
            self.step(5)
            event.accept()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            game = self.current_game()
            if game is not None:
                self.activated.emit(game)
            event.accept()
            return
        if key in (Qt.Key_I, Qt.Key_Up):
            game = self.current_game()
            if game is not None:
                self.details_requested.emit(game)
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - API de Qt
        position = self._hit_test(event.position())
        if position != self._hover_index:
            self._hover_index = position
            lift = 0.0 if position < 0 else 1.0
            self._hover_anim.stop()
            self._hover_anim.setStartValue(self._hover_lift)
            self._hover_anim.setEndValue(lift)
            self._hover_anim.start()
        self.setCursor(Qt.PointingHandCursor if position >= 0 else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._hover_index = -1
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_lift)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API de Qt
        position = self._hit_test(event.position())
        if position < 0:
            return
        if position == self.index:
            game = self.current_game()
            if game is not None:
                self.activated.emit(game)
        else:
            self.index = position
            self._sync()
            self._emit_selection()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - API de Qt
        game = self.current_game()
        if game is not None:
            self.details_requested.emit(game)
        event.accept()

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - API de Qt
        position = self._hit_test(QPointF(event.pos()))
        if position >= 0 and position != self.index:
            self.index = position
            self._sync()
            self._emit_selection()
        game = self.items[position].game if position >= 0 else self.current_game()
        if game is not None:
            self.context_requested.emit(game, event.globalPos())
            event.accept()

    def _layout(self):
        width = self.width()
        height = self.height()
        center_x = width / 2.0
        center_y = height * 0.455
        scale = min(width / 1240.0, 1.18)
        cover_w = CASE_W * max(0.72, scale)
        cover_h = CASE_H * max(0.72, scale) + cover_w * TITLE_BAND_RATIO
        gap = cover_w * 0.86
        return center_x, center_y, cover_w, cover_h, gap

    def _slot_geometry(self, position: float, gap: float, cover_w: float):
        offset = position - self._float
        distance = abs(offset)
        if distance > 3.2:
            return None
        lateral = gap * offset * (1.0 + distance * 0.04) + math.copysign(1.0, offset) * distance * distance * gap * 0.06
        depth = 1.0 / (1.0 + distance * 0.52)
        focus = max(0.0, 1.0 - min(1.0, distance))
        lift = _smooth(1.0 - min(1.0, distance)) * (cover_w * 0.032)
        lift += focus * self._hover_lift * (cover_w * 0.014)
        return {
            "x": lateral,
            "scale": 0.52 + 0.48 * depth,
            "dim": min(0.7, distance * 0.28),
            "lift": lift,
            "focus": focus,
            "distance": distance,
        }

    def _hit_test(self, point: QPointF) -> int:
        if not self.items:
            return -1
        center_x, center_y, cover_w, cover_h, gap = self._layout()
        best = -1
        best_distance = 1e9
        for position in range(len(self.items)):
            geometry = self._slot_geometry(position, gap, cover_w)
            if geometry is None:
                continue
            width = cover_w * geometry["scale"]
            height = cover_h * geometry["scale"]
            left = center_x + geometry["x"] - width / 2.0
            top = center_y - height / 2.0 - geometry["lift"]
            rect = QRectF(left, top, width, height)
            if rect.contains(point):
                distance = abs(point.x() - (left + width / 2.0))
                if distance < best_distance:
                    best_distance = distance
                    best = position
        return best

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.fillRect(self.rect(), QColor(CANVAS_BG))

        center_x, center_y, cover_w, cover_h, gap = self._layout()

        self._paint_backdrop(painter)
        self._paint_halo(painter, center_x, center_y, cover_w, cover_h)
        self._paint_floor(painter, center_x, center_y, cover_w, cover_h)
        paint_scene(
            painter,
            QRectF(self.rect()),
            center_x,
            center_y,
            cover_w,
            cover_h,
            active_style(),
        )

        order: list[tuple[int, float, dict]] = []
        for position in range(len(self.items)):
            geometry = self._slot_geometry(position, gap, cover_w)
            if geometry is None:
                continue
            order.append((position, position - self._float, geometry))
        order.sort(key=lambda entry: -abs(entry[1]))

        for position, _, geometry in order:
            self._paint_case(
                painter,
                self.items[position],
                geometry,
                center_x,
                center_y,
                cover_w,
                cover_h,
                selected=(position == self.index),
            )

        painter.end()

    def _paint_backdrop(self, painter: QPainter) -> None:
        rect = QRectF(self.rect())
        wash = QLinearGradient(0, 0, 0, rect.height())
        wash.setColorAt(0.0, QColor(WASH_TOP))
        wash.setColorAt(0.5, QColor(WASH_MID))
        wash.setColorAt(1.0, QColor(WASH_BOTTOM))
        painter.fillRect(rect, QBrush(wash))

        glow = QRadialGradient(rect.width() * 0.5, rect.height() * 0.42, rect.width() * 0.72)
        main_glow = QColor(HALO_MAIN)
        main_glow.setAlpha(26)
        soft_glow = QColor(HALO_SOFT)
        soft_glow.setAlpha(10)
        glow.setColorAt(0.0, main_glow)
        glow.setColorAt(0.55, soft_glow)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, QBrush(glow))

        vignette = QRadialGradient(
            rect.width() * 0.5, rect.height() * 0.46, max(rect.width(), rect.height()) * 0.72
        )
        vignette.setColorAt(0.35, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 168))
        painter.fillRect(rect, QBrush(vignette))

    def _paint_halo(
        self, painter: QPainter, center_x: float, center_y: float, cover_w: float, cover_h: float
    ) -> None:
        painter.save()
        halo = QRadialGradient(center_x, center_y, cover_w * 1.15)
        halo.setColorAt(0.0, HALO_MAIN)
        halo.setColorAt(0.5, HALO_SOFT)
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(
            QPointF(center_x, center_y), cover_w * 1.15, cover_h * 0.66
        )
        painter.restore()

    def _paint_floor(
        self, painter: QPainter, center_x: float, center_y: float, cover_w: float, cover_h: float
    ) -> None:
        base_y = center_y + cover_h * 0.52
        painter.save()
        shadow = QRadialGradient(center_x, base_y + 6, cover_w * 0.95)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 160))
        shadow.setColorAt(0.6, QColor(0, 0, 0, 70))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QPointF(center_x, base_y + 6), cover_w * 0.72, 22)
        painter.restore()

    def _paint_case(
        self,
        painter: QPainter,
        item: ShelfItem,
        geometry: dict,
        center_x: float,
        center_y: float,
        cover_w: float,
        cover_h: float,
        selected: bool,
    ) -> None:
        width = cover_w * geometry["scale"]
        height = cover_h * geometry["scale"]
        left = center_x + geometry["x"] - width / 2.0
        top = center_y - height / 2.0 - geometry["lift"]
        target = QRectF(left, top, width, height)

        side = 0.0
        offset = geometry["x"]
        if offset > 0.5:
            side = 1.0
        elif offset < -0.5:
            side = -1.0
        tilt_amount = (1.0 - geometry["focus"]) * 0.85 + 0.12

        quad = _perspective_quad(width, height, tilt_amount, side)
        absolute = [
            QPointF(target.center().x() + point.x(), target.center().y() + point.y())
            for point in quad
        ]
        source = [
            QPointF(target.left(), target.top()),
            QPointF(target.right(), target.top()),
            QPointF(target.right(), target.bottom()),
            QPointF(target.left(), target.bottom()),
        ]
        trans = _quad_transform(source, absolute)

        painter.save()
        painter.setTransform(trans, False)
        self._paint_spine(painter, target, item)
        self._paint_front(painter, target, item, selected)
        painter.restore()

        fade = min(0.82, geometry["dim"] * 1.05)
        if fade > 0.01:
            painter.save()
            painter.setTransform(trans, False)
            self._paint_fade(painter, target, fade)
            painter.restore()

        painter.save()
        self._paint_stand(painter, target, geometry, selected)
        painter.restore()

    def _paint_fade(self, painter: QPainter, target: QRectF, fade: float) -> None:
        shade = QColor(6, 5, 3, int(255 * fade))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(shade))
        painter.drawRect(target)

    def _paint_spine(self, painter: QPainter, target: QRectF, item: ShelfItem) -> None:
        width = target.width()
        height = target.height()
        depth = CASE_DEPTH * (width / CASE_W) * 0.55
        path = QPainterPath()
        path.moveTo(target.right(), target.top())
        path.lineTo(target.right() + depth, target.top() + depth * 0.35)
        path.lineTo(target.right() + depth, target.bottom() - depth * 0.35)
        path.lineTo(target.right(), target.bottom())
        path.closeSubpath()
        spine = QLinearGradient(target.right(), 0, target.right() + depth, 0)
        spine.setColorAt(0.0, QColor("#1b1610"))
        spine.setColorAt(1.0, QColor("#0a0806"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(spine))
        painter.drawPath(path)

    def _paint_front(
        self, painter: QPainter, target: QRectF, item: ShelfItem, selected: bool
    ) -> None:
        frame = QRectF(target)
        width = frame.width()
        height = frame.height()
        radius = 3.0
        pc_case = _is_pc_case(item.game)
        band_h = height * (0.15 if pc_case else 0.128)
        title_h = width * TITLE_BAND_RATIO

        title = QRectF(frame.left(), frame.top(), width, title_h)
        art = QRectF(frame.left(), frame.top() + title_h, width, height - band_h - title_h)
        band = QRectF(frame.left(), frame.bottom() - band_h, width, band_h)

        outer = QPainterPath()
        outer.addRoundedRect(frame, radius, radius)
        painter.save()
        painter.setClipPath(outer)

        if item.pixmap is not None:
            src_size = art.size().toSize()
            ratio = item.pixmap.width() / max(1, item.pixmap.height())
            target_ratio = art.width() / max(1.0, art.height())
            if ratio > target_ratio * 1.25:
                painter.fillRect(art, QColor("#080705"))
                small = QSize(
                    max(1, int(src_size.width() * 0.12)),
                    max(1, int(src_size.height() * 0.12)),
                )
                backdrop = item.pixmap.scaled(
                    small, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                ).scaled(src_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                painter.setOpacity(0.42)
                painter.drawPixmap(
                    QPointF(
                        art.center().x() - backdrop.width() / 2,
                        art.center().y() - backdrop.height() / 2,
                    ),
                    backdrop,
                )
                painter.setOpacity(1.0)
                scaled = item.pixmap.scaled(
                    src_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                painter.drawPixmap(
                    QPointF(
                        art.center().x() - scaled.width() / 2,
                        art.center().y() - scaled.height() / 2,
                    ),
                    scaled,
                )
            else:
                src = item.pixmap.scaled(
                    src_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
                sx = max(0, (src.width() - src_size.width()) // 2)
                sy = max(0, (src.height() - src_size.height()) // 2)
                painter.drawPixmap(
                    art.topLeft(), src.copy(sx, sy, src_size.width(), src_size.height())
                )
        else:
            self._paint_placeholder(painter, art, item)

        self._paint_title_band(painter, title, item)

        if pc_case:
            self._paint_pc_band(painter, band, item)
        else:
            self._paint_color_band(painter, band, item, width)

        gloss = QLinearGradient(art.topLeft(), art.bottomLeft())
        gloss.setColorAt(0.0, QColor(255, 244, 220, 22))
        gloss.setColorAt(0.22, QColor(255, 244, 220, 4))
        gloss.setColorAt(1.0, QColor(0, 0, 0, 40))
        painter.fillRect(art, QBrush(gloss))

        style = active_style()
        frame_line = QColor(style.text)
        frame_line.setAlpha(60 if selected else 30)
        painter.setPen(QPen(frame_line, 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(frame.adjusted(0.6, 0.6, -0.6, -0.6), radius, radius)
        painter.restore()

        if selected:
            painter.setPen(QPen(SELECT_GLOW, 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(frame.adjusted(-1.2, -1.2, 1.2, 1.2), radius + 1, radius + 1)

    def _paint_title_band(
        self, painter: QPainter, rect: QRectF, item: ShelfItem
    ) -> None:
        style = active_style()
        base = QColor(style.surface_2)
        accent = QColor(style.accent)
        shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        shade.setColorAt(0.0, _mix(base, QColor(style.bg), 0.28))
        shade.setColorAt(1.0, _mix(base, accent, 0.12))
        painter.fillRect(rect, QBrush(shade))

        line = QColor(accent)
        line.setAlpha(130)
        painter.setPen(QPen(line, 1))
        painter.drawLine(
            QPointF(rect.left(), rect.bottom()), QPointF(rect.right(), rect.bottom())
        )

        font = QFont(style.heading_font or UI_FONT)
        font.setPixelSize(max(8, int(rect.height() * 0.42)))
        font.setWeight(QFont.DemiBold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, rect.height() * 0.04)
        painter.setFont(font)
        painter.setPen(QColor(style.accent_2))

        pad = rect.height() * 0.24
        text_rect = QRectF(
            rect.left() + pad, rect.top(), rect.width() - pad * 2, rect.height()
        )
        title_text = (
            item.game.title.upper() if style.uppercase_headings else item.game.title
        )
        metrics = QFontMetrics(font)
        shown = metrics.elidedText(title_text, Qt.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, shown)

    def _paint_color_band(
        self, painter: QPainter, band: QRectF, item: ShelfItem, width: float
    ) -> None:
        color = _band_color(item.game)
        shade = QLinearGradient(band.topLeft(), band.bottomLeft())
        shade.setColorAt(0.0, color.lighter(108))
        shade.setColorAt(1.0, color.darker(118))
        painter.fillRect(band, QBrush(shade))

        text = _band_text(item.game)
        ink = _readable_on(color)
        font = QFont(UI_FONT)
        font.setPixelSize(max(7, int(band.height() * 0.4)))
        font.setWeight(QFont.Medium)
        font.setLetterSpacing(QFont.AbsoluteSpacing, band.height() * 0.09)
        painter.setFont(font)
        painter.setPen(ink)

        badge_size = band.height() * 0.66
        margin = band.height() * 0.19
        text_rect = QRectF(
            band.left() + margin,
            band.top(),
            band.width() - badge_size - margin * 2.4,
            band.height(),
        )
        metrics = QFontMetrics(font)
        clipped = metrics.elidedText(text.upper(), Qt.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, clipped)

        self._paint_badge(painter, band, item, badge_size, margin)

    def _paint_pc_band(
        self, painter: QPainter, band: QRectF, item: ShelfItem
    ) -> None:
        style = active_style()
        base_color = QColor(style.surface_2)
        accent = QColor(style.accent)
        base = QLinearGradient(band.topLeft(), band.bottomLeft())
        base.setColorAt(0.0, _mix(base_color, accent, 0.12))
        base.setColorAt(1.0, _mix(base_color, QColor(style.bg), 0.35))
        painter.fillRect(band, QBrush(base))

        hairline = QColor(accent)
        hairline.setAlpha(90)
        painter.setPen(QPen(hairline, 1))
        painter.drawLine(
            QPointF(band.left(), band.top()), QPointF(band.right(), band.top())
        )

        ink = _readable_on(_mix(base_color, accent, 0.08))
        if style.key in {"layton", "mario"}:
            ink = _mix(QColor(style.text), QColor(style.bg), 0.2)

        badge_size = band.height() * 0.62
        margin = band.height() * 0.22
        available = band.width() - badge_size - margin * 3.4

        source = (item.game.source or "").lower()
        if source == "steam":
            name = "STEAM"
        elif source == "epic":
            name = "EPIC GAMES"
        elif source == "gog":
            name = "GOG"
        elif item.game.emulator and not _is_pc_case(item.game):
            name = item.game.emulator
        else:
            name = Path(item.game.executable).stem if item.game.executable else "PC"
            if len(name) > 16:
                name = name[:15] + "…"

        font = QFont(UI_FONT)
        font.setPixelSize(max(7, int(band.height() * 0.34)))
        font.setWeight(QFont.Medium)
        font.setLetterSpacing(QFont.AbsoluteSpacing, band.height() * 0.09)
        painter.setFont(font)
        painter.setPen(ink)

        text_rect = QRectF(
            band.left() + margin + band.height() * 0.26,
            band.top(),
            available - band.height() * 0.26,
            band.height(),
        )
        metrics = QFontMetrics(font)
        shown = metrics.elidedText(name.upper(), Qt.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, shown)

        diamond = band.height() * 0.075
        center = QPointF(band.left() + margin + diamond, band.center().y())
        painter.setPen(Qt.NoPen)
        marker = QColor(accent)
        marker.setAlpha(170)
        painter.setBrush(marker)
        path = QPainterPath()
        path.moveTo(center.x(), center.y() - diamond)
        path.lineTo(center.x() + diamond, center.y())
        path.lineTo(center.x(), center.y() + diamond)
        path.lineTo(center.x() - diamond, center.y())
        path.closeSubpath()
        painter.drawPath(path)

        self._paint_badge(painter, band, item, badge_size, margin)

    def _paint_badge(
        self, painter: QPainter, band: QRectF, item: ShelfItem, size: float, margin: float
    ) -> None:
        pixmap = _exe_badge(item.game.executable)
        plate = QRectF(
            band.right() - margin - size,
            band.top() + (band.height() - size) / 2.0,
            size,
            size,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 52))
        painter.drawRoundedRect(plate, size * 0.22, size * 0.22)
        if pixmap is not None and not pixmap.isNull():
            painter.drawPixmap(plate, pixmap, QRectF(pixmap.rect()))

    def _paint_placeholder(self, painter: QPainter, frame: QRectF, item: ShelfItem) -> None:
        style = active_style()
        accent = QColor(style.accent)
        base = QLinearGradient(frame.topLeft(), frame.bottomRight())
        base.setColorAt(0.0, QColor(style.surface_2))
        base.setColorAt(0.55, _mix(accent, QColor(style.bg), 0.86))
        base.setColorAt(1.0, _mix(accent, QColor(style.bg), 0.7))
        painter.fillRect(frame, QBrush(base))

        line = QColor(style.accent)
        line.setAlpha(28)
        painter.setPen(QPen(line, 1))
        painter.setBrush(Qt.NoBrush)
        inset = frame.adjusted(9, 9, -9, -9)
        painter.drawRect(inset)

        initials = "".join(word[0] for word in item.game.title.split()[:2]).upper() or "?"
        font = QFont(UI_FONT)
        font.setPixelSize(int(frame.height() * 0.3))
        font.setWeight(QFont.Medium)
        font.setLetterSpacing(QFont.AbsoluteSpacing, frame.width() * 0.03)
        painter.setFont(font)
        text_color = QColor(style.text)
        text_color.setAlpha(70)
        painter.setPen(text_color)
        painter.drawText(frame, Qt.AlignCenter, initials)

        painter.setPen(QPen(QColor(style.accent), 1))
        painter.setOpacity(0.4)
        line_y = frame.center().y() + frame.height() * 0.14
        painter.drawLine(
            QPointF(frame.center().x() - frame.width() * 0.16, line_y),
            QPointF(frame.center().x() + frame.width() * 0.16, line_y),
        )
        painter.setOpacity(1.0)

    def _paint_stand(
        self, painter: QPainter, target: QRectF, geometry: dict, selected: bool
    ) -> None:
        focus = geometry["focus"]
        strength = focus if selected else focus * 0.45
        if strength <= 0.02:
            return
        base_y = target.bottom() + 3
        width = target.width()
        height = target.height()

        reflection = QLinearGradient(0, base_y, 0, base_y + height * 0.14)
        accent = QColor(active_style().accent)
        glow = QColor(accent)
        glow.setAlpha(int(26 * strength))
        mid = QColor(accent)
        mid.setAlpha(int(9 * strength))
        reflection.setColorAt(0.0, glow)
        reflection.setColorAt(0.55, mid)
        reflection.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        painter.fillRect(
            QRectF(target.left(), base_y, width, height * 0.14), QBrush(reflection)
        )

        pool = QRadialGradient(target.center().x(), base_y + 4, width * 0.62)
        center = QColor(accent)
        center.setAlpha(int(44 * strength))
        edge = QColor(accent)
        edge.setAlpha(int(16 * strength))
        pool.setColorAt(0.0, center)
        pool.setColorAt(0.55, edge)
        pool.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(pool))
        painter.drawEllipse(
            QPointF(target.center().x(), base_y + 4), width * 0.62, height * 0.032
        )

        shadow = QRadialGradient(target.center().x(), base_y, width * 0.5)
        shadow.setColorAt(0.0, QColor(0, 0, 0, int(160 * max(0.3, strength))))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(
            QPointF(target.center().x(), base_y), width * 0.4, height * 0.02
        )
