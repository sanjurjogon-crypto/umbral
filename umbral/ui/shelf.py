from __future__ import annotations

import math
import os
from collections import OrderedDict
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
    QImage,
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


@dataclass(frozen=True)
class CaseProfile:
    key: str
    w_scale: float
    h_scale: float
    radius: float
    spine_color: str
    header_bg: str
    header_accent: str
    header_text: str
    band_label: str
    depth_scale: float = 1.0


CASE_PROFILES: dict[str, CaseProfile] = {
    "switch2": CaseProfile(
        key="switch2",
        w_scale=0.80,
        h_scale=1.08,
        radius=6.0,
        spine_color="#c62828",
        header_bg="#b71c1c",
        header_accent="#ff5252",
        header_text="#ffffff",
        band_label="SWITCH 2",
        depth_scale=0.72,
    ),
    "switch": CaseProfile(
        key="switch",
        w_scale=0.80,
        h_scale=1.06,
        radius=6.0,
        spine_color="#e60012",
        header_bg="#d50010",
        header_accent="#ff6b6b",
        header_text="#ffffff",
        band_label="SWITCH",
        depth_scale=0.72,
    ),
    "3ds": CaseProfile(
        key="3ds",
        w_scale=0.96,
        h_scale=0.82,
        radius=6.0,
        spine_color="#e5e8ed",
        header_bg="#f2f4f7",
        header_accent="#d32f2f",
        header_text="#17191c",
        band_label="NINTENDO 3DS",
        depth_scale=0.88,
    ),
    "nds": CaseProfile(
        key="nds",
        w_scale=0.95,
        h_scale=0.80,
        radius=5.0,
        spine_color="#2c3038",
        header_bg="#23272e",
        header_accent="#9ca3af",
        header_text="#f3f4f6",
        band_label="NINTENDO DS",
        depth_scale=0.90,
    ),
    "ps3": CaseProfile(
        key="ps3",
        w_scale=0.90,
        h_scale=0.96,
        radius=6.0,
        spine_color="#1a1f28",
        header_bg="#0e1117",
        header_accent="#b8c4d8",
        header_text="#eef2f8",
        band_label="PLAYSTATION 3",
        depth_scale=0.84,
    ),
    "ps2": CaseProfile(
        key="ps2",
        w_scale=0.92,
        h_scale=1.00,
        radius=4.0,
        spine_color="#112b5c",
        header_bg="#0b1d40",
        header_accent="#4b83e8",
        header_text="#edf2ff",
        band_label="PLAYSTATION 2",
        depth_scale=0.92,
    ),
    "ps1": CaseProfile(
        key="ps1",
        w_scale=0.98,
        h_scale=0.84,
        radius=3.0,
        spine_color="#25272c",
        header_bg="#181a1f",
        header_accent="#9aa0aa",
        header_text="#f1f5f9",
        band_label="PLAYSTATION",
        depth_scale=0.76,
    ),
    "psp": CaseProfile(
        key="psp",
        w_scale=0.78,
        h_scale=1.02,
        radius=7.0,
        spine_color="#2a2d35",
        header_bg="#13161d",
        header_accent="#7dd3fc",
        header_text="#f8fafc",
        band_label="PSP",
        depth_scale=0.78,
    ),
    "psvita": CaseProfile(
        key="psvita",
        w_scale=0.82,
        h_scale=0.94,
        radius=6.0,
        spine_color="#0052cc",
        header_bg="#003d99",
        header_accent="#38bdf8",
        header_text="#ffffff",
        band_label="PS VITA",
        depth_scale=0.72,
    ),
    "wii": CaseProfile(
        key="wii",
        w_scale=0.92,
        h_scale=1.00,
        radius=5.0,
        spine_color="#e9edf2",
        header_bg="#f4f6f9",
        header_accent="#38bdf8",
        header_text="#1e293b",
        band_label="WII / GC",
        depth_scale=0.92,
    ),
    "wiiu": CaseProfile(
        key="wiiu",
        w_scale=0.92,
        h_scale=1.00,
        radius=5.0,
        spine_color="#009ac7",
        header_bg="#007ca3",
        header_accent="#67e8f9",
        header_text="#ffffff",
        band_label="WII U",
        depth_scale=0.92,
    ),
    "xbox360": CaseProfile(
        key="xbox360",
        w_scale=0.92,
        h_scale=1.00,
        radius=5.0,
        spine_color="#1d6f1d",
        header_bg="#145214",
        header_accent="#7ed321",
        header_text="#ffffff",
        band_label="XBOX 360",
        depth_scale=0.92,
    ),
    "xbox": CaseProfile(
        key="xbox",
        w_scale=0.92,
        h_scale=1.00,
        radius=5.0,
        spine_color="#105c10",
        header_bg="#0c420c",
        header_accent="#4ade80",
        header_text="#ffffff",
        band_label="XBOX",
        depth_scale=0.92,
    ),
    "ports": CaseProfile(
        key="ports",
        w_scale=0.98,
        h_scale=0.98,
        radius=4.0,
        spine_color="#2a2214",
        header_bg="#19150d",
        header_accent="#d4af37",
        header_text="#efe0b4",
        band_label="PORT",
        depth_scale=0.95,
    ),
    "steam": CaseProfile(
        key="steam",
        w_scale=1.00,
        h_scale=1.00,
        radius=3.5,
        spine_color="#1b2b3f",
        header_bg="#14202e",
        header_accent="#66c0f4",
        header_text="#d8ecff",
        band_label="STEAM",
        depth_scale=1.0,
    ),
    "epic": CaseProfile(
        key="epic",
        w_scale=1.00,
        h_scale=1.00,
        radius=3.5,
        spine_color="#22252b",
        header_bg="#16181d",
        header_accent="#d4d8df",
        header_text="#f4f6f8",
        band_label="EPIC GAMES",
        depth_scale=1.0,
    ),
    "gog": CaseProfile(
        key="gog",
        w_scale=1.00,
        h_scale=1.00,
        radius=3.5,
        spine_color="#3b2059",
        header_bg="#26143b",
        header_accent="#b77bff",
        header_text="#f2e7ff",
        band_label="GOG",
        depth_scale=1.0,
    ),
    "pc": CaseProfile(
        key="pc",
        w_scale=1.00,
        h_scale=1.00,
        radius=3.0,
        spine_color="#221c13",
        header_bg="#16120c",
        header_accent="#d4af37",
        header_text="#efe0b4",
        band_label="PC",
        depth_scale=1.0,
    ),
}


def case_profile(game: Game) -> CaseProfile:
    """Return physical box dimensions and system styling for a game."""
    source = (game.source or "").strip().lower()
    sys_key = (game.system_key or "").strip().lower()
    if sys_key in CASE_PROFILES and sys_key not in {"pc", "ports"}:
        return CASE_PROFILES[sys_key]
    if source in CASE_PROFILES:
        return CASE_PROFILES[source]
    if sys_key in CASE_PROFILES:
        return CASE_PROFILES[sys_key]
    if not _is_pc_case(game):
        band_col = _band_color(game)
        return CaseProfile(
            key=sys_key or "retro",
            w_scale=0.94,
            h_scale=0.94,
            radius=4.0,
            spine_color=band_col.darker(155).name(),
            header_bg=band_col.darker(175).name(),
            header_accent=band_col.name(),
            header_text="#f5f7fb",
            band_label=_band_text(game).upper(),
            depth_scale=0.9,
        )
    return CASE_PROFILES["pc"]


def _dominant_color(pixmap: Optional[QPixmap], fallback: QColor) -> QColor:
    """Extract a vivid accent color from a game's cover artwork."""
    if pixmap is None or pixmap.isNull():
        return QColor(fallback)
    tiny = pixmap.scaled(12, 12, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).toImage()
    if tiny.isNull():
        return QColor(fallback)
    best: Optional[QColor] = None
    best_score = -1.0
    red_sum = 0.0
    green_sum = 0.0
    blue_sum = 0.0
    count = 0
    for y in range(tiny.height()):
        for x in range(tiny.width()):
            color = tiny.pixelColor(x, y)
            if color.alpha() < 128:
                continue
            r, g, b = color.red(), color.green(), color.blue()
            red_sum += r
            green_sum += g
            blue_sum += b
            count += 1
            max_c = max(r, g, b)
            min_c = min(r, g, b)
            sat = (max_c - min_c) / max(1, max_c)
            lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
            mid_weight = 1.0 - abs(lum - 0.55) * 1.1
            score = sat * max(0.25, mid_weight) * (max_c / 255.0)
            if score > best_score:
                best_score = score
                best = color
    if best is not None and best_score > 0.18:
        h, s, v, _ = best.getHsvF()
        return QColor.fromHsvF(max(0.0, h), max(0.55, min(0.95, s)), max(0.65, min(0.95, v)))
    if count > 0:
        avg = QColor(int(red_sum / count), int(green_sum / count), int(blue_sum / count))
        return _mix(avg, QColor(fallback), 0.35)
    return QColor(fallback)


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


def _perspective_quad(
    width: float,
    height: float,
    tilt: float,
    side: float,
    hover_x: float = 0.0,
    hover_y: float = 0.0,
) -> list[QPointF]:
    half_w = width / 2.0
    half_h = height / 2.0
    inset = half_w * 0.11 * tilt
    top_inset = inset
    bottom_inset = inset * 0.18
    shift = side * half_w * 0.045 * tilt
    mouse_dx = hover_x * half_w * 0.05
    mouse_dy = hover_y * half_h * 0.038
    return [
        QPointF(-half_w + top_inset + shift * 0.4 + mouse_dx * 0.45, -half_h + inset * 0.12 - mouse_dy),
        QPointF(half_w - top_inset * 0.35 + shift + mouse_dx * 0.45, -half_h - inset * 0.12 + mouse_dy * 0.65),
        QPointF(half_w - bottom_inset + shift - mouse_dx * 0.45, half_h - inset * 0.05 - mouse_dy * 0.65),
        QPointF(-half_w + bottom_inset * 0.35 + shift * 0.4 - mouse_dx * 0.45, half_h + inset * 0.05 + mouse_dy),
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
    profile: CaseProfile
    dominant: QColor


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
        self._tilt_x = 0.0
        self._tilt_y = 0.0
        self._tilt_target_x = 0.0
        self._tilt_target_y = 0.0
        self._backdrop_mix = 1.0
        self._prev_backdrop_pixmap: Optional[QPixmap] = None
        self._prev_backdrop_color: Optional[QColor] = None
        self._active_backdrop_id: str = ""
        self._backdrop_cache: OrderedDict[tuple[str, int, int], QPixmap] = OrderedDict()

        self._anim = QPropertyAnimation(self, b"position", self)
        self._anim.setDuration(520)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self._hover_anim = QPropertyAnimation(self, b"hover_lift", self)
        self._hover_anim.setDuration(220)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._bg_anim = QPropertyAnimation(self, b"backdrop_mix", self)
        self._bg_anim.setDuration(420)
        self._bg_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._tilt_timer = QTimer(self)
        self._tilt_timer.setInterval(16)
        self._tilt_timer.timeout.connect(self._step_tilt)

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

    def get_backdrop_mix(self) -> float:
        return self._backdrop_mix

    def set_backdrop_mix(self, value: float) -> None:
        self._backdrop_mix = float(value)
        self.update()

    backdrop_mix = Property(float, get_backdrop_mix, set_backdrop_mix)

    def _step_tilt(self) -> None:
        dx = self._tilt_target_x - self._tilt_x
        dy = self._tilt_target_y - self._tilt_y
        if abs(dx) < 0.008 and abs(dy) < 0.008:
            self._tilt_x = self._tilt_target_x
            self._tilt_y = self._tilt_target_y
            self._tilt_timer.stop()
        else:
            self._tilt_x += dx * 0.24
            self._tilt_y += dy * 0.24
        self.update()

    def set_games(self, games: list[Game]) -> None:
        previous = self.current_game()
        fallback = QColor(active_style().accent)
        items: list[ShelfItem] = []
        for game in games:
            pixmap = self._load(game)
            profile = case_profile(game)
            dominant = _dominant_color(pixmap, QColor(profile.header_accent or fallback.name()))
            items.append(ShelfItem(game, pixmap, profile, dominant))
        self.items = items
        self._backdrop_cache.clear()
        self.index = 0
        if previous is not None:
            for position, item in enumerate(self.items):
                if item.game.id == previous.id:
                    self.index = position
                    break
        self.index = max(0, min(self.index, len(self.items) - 1))
        self._float = float(self.index)
        self._target = self._float
        current_item = self._current_item()
        self._active_backdrop_id = current_item.game.id if current_item else ""
        self._prev_backdrop_pixmap = None
        self._prev_backdrop_color = None
        self._backdrop_mix = 1.0
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

    def _current_item(self) -> Optional[ShelfItem]:
        if 0 <= self.index < len(self.items):
            return self.items[self.index]
        return None

    def _sync(self) -> None:
        self._anim.stop()
        target = float(self.index)
        self._anim.setStartValue(self._float)
        self._anim.setEndValue(target)
        self._anim.start()
        self.update()

    def _start_backdrop_transition(self, previous: Optional[ShelfItem], current: Optional[ShelfItem]) -> None:
        cur_id = current.game.id if current is not None else ""
        if cur_id == self._active_backdrop_id:
            return
        self._prev_backdrop_pixmap = previous.pixmap if previous is not None else None
        self._prev_backdrop_color = previous.dominant if previous is not None else None
        self._active_backdrop_id = cur_id
        self._bg_anim.stop()
        self._backdrop_mix = 0.0
        self._bg_anim.setStartValue(0.0)
        self._bg_anim.setEndValue(1.0)
        self._bg_anim.start()

    def _emit_selection(self) -> None:
        game = self.current_game()
        if game is not None:
            self.selection_changed.emit(game)
        self.update()

    def step(self, delta: int) -> None:
        if not self.items:
            return
        previous_item = self._current_item()
        new_index = max(0, min(self.index + delta, len(self.items) - 1))
        self.index = new_index
        current_item = self._current_item()
        if new_index != (self.items.index(previous_item) if previous_item in self.items else -1):
            self._start_backdrop_transition(previous_item, current_item)
        self._sync()
        self._emit_selection()

    def moveEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().moveEvent(event)
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().resizeEvent(event)
        self._backdrop_cache.clear()
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
        point = event.position()
        position = self._hit_test(point)
        if position != self._hover_index:
            self._hover_index = position
            lift = 0.0 if position < 0 else 1.0
            self._hover_anim.stop()
            self._hover_anim.setStartValue(self._hover_lift)
            self._hover_anim.setEndValue(lift)
            self._hover_anim.start()
        if position == self.index and position >= 0:
            center_x, center_y, cover_w, cover_h, _gap = self._layout()
            item = self.items[position]
            half_w = max(1.0, (cover_w * item.profile.w_scale) / 2.0)
            half_h = max(1.0, (cover_h * item.profile.h_scale) / 2.0)
            self._tilt_target_x = max(-1.0, min(1.0, (point.x() - center_x) / half_w))
            self._tilt_target_y = max(-1.0, min(1.0, (point.y() - center_y) / half_h))
        else:
            self._tilt_target_x = 0.0
            self._tilt_target_y = 0.0
        if not self._tilt_timer.isActive() and (
            abs(self._tilt_target_x - self._tilt_x) > 0.008
            or abs(self._tilt_target_y - self._tilt_y) > 0.008
        ):
            self._tilt_timer.start()
        self.setCursor(Qt.PointingHandCursor if position >= 0 else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._hover_index = -1
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_lift)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()
        self._tilt_target_x = 0.0
        self._tilt_target_y = 0.0
        if not self._tilt_timer.isActive() and (
            abs(self._tilt_x) > 0.008 or abs(self._tilt_y) > 0.008
        ):
            self._tilt_timer.start()
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
            self.step(position - self.index)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - API de Qt
        game = self.current_game()
        if game is not None:
            self.details_requested.emit(game)
        event.accept()

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - API de Qt
        position = self._hit_test(QPointF(event.pos()))
        if position >= 0 and position != self.index:
            self.step(position - self.index)
        game = self.items[position].game if position >= 0 else self.current_game()
        if game is not None:
            self.context_requested.emit(game, event.globalPos())
            event.accept()

    def _layout(self):
        width = self.width()
        height = self.height()
        center_x = width / 2.0
        center_y = height * 0.445
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
        lift += focus * self._hover_lift * (cover_w * 0.016)
        return {
            "x": lateral,
            "scale": 0.52 + 0.48 * depth,
            "dim": min(0.7, distance * 0.28),
            "lift": lift,
            "focus": focus,
            "distance": distance,
        }

    def _case_rect(
        self,
        item: ShelfItem,
        geometry: dict,
        center_x: float,
        center_y: float,
        cover_w: float,
        cover_h: float,
    ) -> QRectF:
        width = cover_w * item.profile.w_scale * geometry["scale"]
        height = cover_h * item.profile.h_scale * geometry["scale"]
        # Align bottom edges along a consistent shelf plane so taller/shorter cases rest naturally
        shelf_floor = center_y + cover_h * 0.50
        bottom = shelf_floor - geometry["lift"] - (cover_h * 0.50 * (1.0 - geometry["scale"]))
        top = bottom - height
        left = center_x + geometry["x"] - width / 2.0
        return QRectF(left, top, width, height)

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
            rect = self._case_rect(
                self.items[position], geometry, center_x, center_y, cover_w, cover_h
            )
            if rect.contains(point):
                distance = abs(point.x() - rect.center().x())
                if distance < best_distance:
                    best_distance = distance
                    best = position
        return best

    def _blurred_backdrop(self, key: str, pixmap: QPixmap, size: QSize) -> QPixmap:
        cache_key = (key, size.width(), size.height())
        cached = self._backdrop_cache.get(cache_key)
        if cached is not None:
            self._backdrop_cache.move_to_end(cache_key)
            return cached
        small_w = max(18, size.width() // 18)
        small_h = max(12, size.height() // 18)
        tiny = pixmap.scaled(small_w, small_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        blurred = tiny.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        sx = max(0, (blurred.width() - size.width()) // 2)
        sy = max(0, (blurred.height() - size.height()) // 2)
        cropped = blurred.copy(sx, sy, size.width(), size.height())
        self._backdrop_cache[cache_key] = cropped
        if len(self._backdrop_cache) > 24:
            self._backdrop_cache.popitem(last=False)
        return cropped

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.fillRect(self.rect(), QColor(CANVAS_BG))

        center_x, center_y, cover_w, cover_h, gap = self._layout()
        current_item = self._current_item()

        self._paint_backdrop(painter, current_item, center_x, center_y, cover_w, cover_h)
        paint_scene(
            painter,
            QRectF(self.rect()),
            center_x,
            center_y,
            cover_w,
            cover_h,
            active_style(),
        )
        self._paint_floor(painter, current_item, center_x, center_y, cover_w, cover_h)

        order: list[tuple[int, float, dict]] = []
        for position in range(len(self.items)):
            geometry = self._slot_geometry(position, gap, cover_w)
            if geometry is None:
                continue
            order.append((position, position - self._float, geometry))
        order.sort(key=lambda entry: -abs(entry[1]))

        for position, _, geometry in order:
            self._paint_reflection(
                painter,
                self.items[position],
                geometry,
                center_x,
                center_y,
                cover_w,
                cover_h,
                selected=(position == self.index),
            )

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

    def _blended_dominant(self, current_item: Optional[ShelfItem]) -> QColor:
        fallback = QColor(active_style().accent)
        target_color = current_item.dominant if current_item is not None else fallback
        if self._prev_backdrop_color is not None and self._backdrop_mix < 1.0:
            return _mix(self._prev_backdrop_color, target_color, self._backdrop_mix)
        return target_color

    def _paint_backdrop(
        self,
        painter: QPainter,
        current_item: Optional[ShelfItem],
        center_x: float,
        center_y: float,
        cover_w: float,
        cover_h: float,
    ) -> None:
        rect = QRectF(self.rect())
        wash = QLinearGradient(0, 0, 0, rect.height())
        wash.setColorAt(0.0, QColor(WASH_TOP))
        wash.setColorAt(0.5, QColor(WASH_MID))
        wash.setColorAt(1.0, QColor(WASH_BOTTOM))
        painter.fillRect(rect, QBrush(wash))

        size = self.size()
        mix = _smooth(self._backdrop_mix)
        if self._prev_backdrop_pixmap is not None and not self._prev_backdrop_pixmap.isNull() and mix < 0.99:
            prev_blur = self._blurred_backdrop("prev", self._prev_backdrop_pixmap, size)
            painter.save()
            painter.setOpacity(0.42 * (1.0 - mix))
            painter.drawPixmap(0, 0, prev_blur)
            painter.restore()
        if current_item is not None and current_item.pixmap is not None and not current_item.pixmap.isNull():
            cur_blur = self._blurred_backdrop(current_item.game.id, current_item.pixmap, size)
            painter.save()
            painter.setOpacity(0.42 * mix)
            painter.drawPixmap(0, 0, cur_blur)
            painter.restore()

        # Rich gradient veil so top header and bottom info stay legible while keeping cover color vivid
        veil = QLinearGradient(0, 0, 0, rect.height())
        veil.setColorAt(0.0, QColor(8, 7, 6, 175))
        veil.setColorAt(0.28, QColor(8, 7, 6, 80))
        veil.setColorAt(0.60, QColor(6, 5, 4, 130))
        veil.setColorAt(1.0, QColor(4, 4, 3, 225))
        painter.fillRect(rect, QBrush(veil))

        dominant = self._blended_dominant(current_item)
        # Ambient color aura behind centered box
        glow = QRadialGradient(center_x, center_y, max(rect.width() * 0.55, cover_w * 1.9))
        c1 = QColor(dominant)
        c1.setAlpha(95)
        c2 = QColor(dominant)
        c2.setAlpha(32)
        glow.setColorAt(0.0, c1)
        glow.setColorAt(0.48, c2)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, QBrush(glow))

        # Overhead spotlight cone onto centered box
        spot = QRadialGradient(center_x, rect.top() + rect.height() * 0.08, cover_h * 1.55)
        s1 = QColor(dominant).lighter(145)
        s1.setAlpha(58)
        spot.setColorAt(0.0, s1)
        spot.setColorAt(0.6, QColor(dominant.red(), dominant.green(), dominant.blue(), 14))
        spot.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, QBrush(spot))

        vignette = QRadialGradient(
            rect.width() * 0.5, rect.height() * 0.46, max(rect.width(), rect.height()) * 0.72
        )
        vignette.setColorAt(0.35, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 175))
        painter.fillRect(rect, QBrush(vignette))

    def _paint_floor(
        self,
        painter: QPainter,
        current_item: Optional[ShelfItem],
        center_x: float,
        center_y: float,
        cover_w: float,
        cover_h: float,
    ) -> None:
        rect = QRectF(self.rect())
        floor_y = center_y + cover_h * 0.50 + 2
        dominant = self._blended_dominant(current_item)

        floor_rect = QRectF(0, floor_y, rect.width(), max(0.0, rect.bottom() - floor_y))
        marble = QLinearGradient(0, floor_y, 0, rect.bottom())
        marble.setColorAt(0.0, QColor(dominant.red(), dominant.green(), dominant.blue(), 28))
        marble.setColorAt(0.25, QColor(12, 11, 10, 165))
        marble.setColorAt(1.0, QColor(4, 4, 3, 235))
        painter.fillRect(floor_rect, QBrush(marble))

        sheen = QLinearGradient(0, floor_y, rect.width(), floor_y)
        sheen.setColorAt(0.0, QColor(0, 0, 0, 0))
        sheen.setColorAt(0.28, QColor(dominant.red(), dominant.green(), dominant.blue(), 45))
        sheen.setColorAt(0.50, QColor(255, 250, 238, 85))
        sheen.setColorAt(0.72, QColor(dominant.red(), dominant.green(), dominant.blue(), 45))
        sheen.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(QPen(QBrush(sheen), 1.3))
        painter.drawLine(QPointF(0, floor_y), QPointF(rect.width(), floor_y))

        painter.save()
        shadow = QRadialGradient(center_x, floor_y + 6, cover_w * 1.05)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 165))
        shadow.setColorAt(0.6, QColor(0, 0, 0, 75))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QPointF(center_x, floor_y + 6), cover_w * 0.84, 24)
        painter.restore()

    def _paint_reflection(
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
        focus = geometry["focus"]
        strength = max(0.18, focus) * (1.0 - min(0.75, geometry["dim"] * 0.9))
        if strength <= 0.08:
            return
        target = self._case_rect(item, geometry, center_x, center_y, cover_w, cover_h)
        refl_h = target.height() * 0.42
        refl_top = target.bottom() + 4.0
        refl_rect = QRectF(target.left(), refl_top, target.width(), refl_h)

        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(refl_rect, item.profile.radius, item.profile.radius)
        painter.setClipPath(clip)

        # Flip lower half of the case artwork onto the crystal floor
        painter.setOpacity(0.42 * strength if selected else 0.26 * strength)
        if item.pixmap is not None and not item.pixmap.isNull():
            src_h = item.pixmap.height()
            slice_h = max(1, int(src_h * 0.48))
            bottom_slice = item.pixmap.copy(0, src_h - slice_h, item.pixmap.width(), slice_h)
            flipped = bottom_slice.transformed(QTransform().scale(1.0, -1.0))
            band_slice_h = refl_h * 0.28
            painter.fillRect(
                QRectF(refl_rect.left(), refl_top, refl_rect.width(), band_slice_h),
                QColor(item.profile.header_bg),
            )
            art_refl = QRectF(
                refl_rect.left(),
                refl_top + band_slice_h,
                refl_rect.width(),
                refl_h - band_slice_h,
            )
            painter.drawPixmap(art_refl, flipped, QRectF(flipped.rect()))
        else:
            fallback = QLinearGradient(refl_rect.topLeft(), refl_rect.bottomLeft())
            fallback.setColorAt(0.0, item.dominant)
            fallback.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(refl_rect, QBrush(fallback))

        painter.setOpacity(1.0)
        fade = QLinearGradient(0, refl_top, 0, refl_rect.bottom())
        fade.setColorAt(0.0, QColor(6, 5, 4, 55))
        fade.setColorAt(0.55, QColor(6, 5, 4, 175))
        fade.setColorAt(1.0, QColor(4, 4, 3, 255))
        painter.fillRect(refl_rect, QBrush(fade))
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
        target = self._case_rect(item, geometry, center_x, center_y, cover_w, cover_h)

        side = 0.0
        offset = geometry["x"]
        if offset > 0.5:
            side = 1.0
        elif offset < -0.5:
            side = -1.0
        tilt_amount = (1.0 - geometry["focus"]) * 0.85 + 0.12
        hover_x = self._tilt_x * geometry["focus"] if selected else 0.0
        hover_y = self._tilt_y * geometry["focus"] if selected else 0.0

        quad = _perspective_quad(
            target.width(), target.height(), tilt_amount, side, hover_x=hover_x, hover_y=hover_y
        )
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
        self._paint_front(painter, target, item, selected, geometry["focus"])
        painter.restore()

        fade = min(0.82, geometry["dim"] * 1.05)
        if fade > 0.01:
            painter.save()
            painter.setTransform(trans, False)
            self._paint_fade(painter, target, fade)
            painter.restore()

        painter.save()
        self._paint_stand(painter, target, item, geometry, selected)
        painter.restore()

    def _paint_fade(self, painter: QPainter, target: QRectF, fade: float) -> None:
        shade = QColor(6, 5, 3, int(255 * fade))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(shade))
        painter.drawRect(target)

    def _paint_spine(self, painter: QPainter, target: QRectF, item: ShelfItem) -> None:
        width = target.width()
        depth = CASE_DEPTH * (width / CASE_W) * 0.55 * item.profile.depth_scale
        path = QPainterPath()
        path.moveTo(target.right(), target.top())
        path.lineTo(target.right() + depth, target.top() + depth * 0.35)
        path.lineTo(target.right() + depth, target.bottom() - depth * 0.35)
        path.lineTo(target.right(), target.bottom())
        path.closeSubpath()
        base = QColor(item.profile.spine_color)
        spine = QLinearGradient(target.right(), 0, target.right() + depth, 0)
        spine.setColorAt(0.0, base)
        spine.setColorAt(1.0, base.darker(190))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(spine))
        painter.drawPath(path)

    def _paint_front(
        self,
        painter: QPainter,
        target: QRectF,
        item: ShelfItem,
        selected: bool,
        focus: float,
    ) -> None:
        frame = QRectF(target)
        width = frame.width()
        height = frame.height()
        profile = item.profile
        radius = profile.radius
        pc_case = _is_pc_case(item.game)
        band_h = height * (0.145 if pc_case else 0.125)
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

        self._paint_status_badges(painter, art, item)

        # Static + interactive specular sheen shifting with mouse tilt on focused box
        sheen_shift = (self._tilt_x * 0.32 if selected else 0.0) * focus
        sheen = QLinearGradient(
            QPointF(frame.left() + width * (0.15 + sheen_shift), frame.top()),
            QPointF(frame.left() + width * (0.75 + sheen_shift), frame.bottom()),
        )
        peak_alpha = int((42 if selected else 22) + abs(self._tilt_x) * 26 * focus)
        sheen.setColorAt(0.0, QColor(255, 248, 232, 0))
        sheen.setColorAt(0.32, QColor(255, 248, 232, peak_alpha))
        sheen.setColorAt(0.50, QColor(255, 255, 255, int(peak_alpha * 0.45)))
        sheen.setColorAt(0.75, QColor(0, 0, 0, 12))
        sheen.setColorAt(1.0, QColor(0, 0, 0, 42))
        painter.fillRect(frame, QBrush(sheen))

        frame_line = QColor(profile.header_accent) if profile.key in {"switch", "switch2", "3ds", "ps3"} else QColor(active_style().text)
        frame_line.setAlpha(120 if selected else 48)
        painter.setPen(QPen(frame_line, 1.3))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(frame.adjusted(0.6, 0.6, -0.6, -0.6), radius, radius)
        painter.restore()

        if selected:
            glow = QColor(item.dominant)
            glow.setAlpha(165)
            painter.setPen(QPen(glow, 1.8))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(frame.adjusted(-1.4, -1.4, 1.4, 1.4), radius + 1.2, radius + 1.2)

    def _paint_status_badges(self, painter: QPainter, art: QRectF, item: ShelfItem) -> None:
        badges: list[tuple[str, QColor, QColor]] = []
        if item.game.favorite:
            badges.append(("star", QColor("#14120d"), QColor("#e8c45e")))
        if item.game.state == "finished":
            badges.append(("check", QColor("#101712"), QColor("#8bc382")))
        if not badges:
            return
        pill_size = max(14.0, min(22.0, art.width() * 0.115))
        pad = max(5.0, art.width() * 0.04)
        gap = max(4.0, pill_size * 0.25)
        painter.save()
        x = art.right() - pad - pill_size
        y = art.top() + pad
        for kind, bg, fg in badges:
            pill = QRectF(x, y, pill_size, pill_size)
            bg_c = QColor(bg)
            bg_c.setAlpha(218)
            border_c = QColor(fg)
            border_c.setAlpha(195)
            painter.setPen(QPen(border_c, 1.1))
            painter.setBrush(bg_c)
            painter.drawRoundedRect(pill, pill_size * 0.3, pill_size * 0.3)

            cx, cy = pill.center().x(), pill.center().y()
            if kind == "star":
                outer_r = pill_size * 0.30
                inner_r = outer_r * 0.44
                star = QPainterPath()
                for idx in range(10):
                    angle = math.radians(-90 + idx * 36)
                    radius = outer_r if idx % 2 == 0 else inner_r
                    pt = QPointF(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)
                    if idx == 0:
                        star.moveTo(pt)
                    else:
                        star.lineTo(pt)
                star.closeSubpath()
                painter.setPen(Qt.NoPen)
                painter.setBrush(fg)
                painter.drawPath(star)
            else:
                check = QPainterPath()
                r = pill_size * 0.25
                check.moveTo(cx - r * 0.95, cy + r * 0.05)
                check.lineTo(cx - r * 0.2, cy + r * 0.8)
                check.lineTo(cx + r * 1.0, cy - r * 0.7)
                pen = QPen(fg, max(1.6, pill_size * 0.12), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(check)

            x -= pill_size + gap
        painter.restore()

    def _paint_title_band(
        self, painter: QPainter, rect: QRectF, item: ShelfItem
    ) -> None:
        style = active_style()
        profile = item.profile
        base = QColor(profile.header_bg)
        accent = QColor(profile.header_accent)
        shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        shade.setColorAt(0.0, base.lighter(114))
        shade.setColorAt(1.0, base.darker(118))
        painter.fillRect(rect, QBrush(shade))

        line = QColor(accent)
        line.setAlpha(180)
        painter.setPen(QPen(line, 1.1))
        painter.drawLine(
            QPointF(rect.left(), rect.bottom()), QPointF(rect.right(), rect.bottom())
        )

        # Tiny Switch/3DS/PS accent bar on left edge of header
        if profile.key in {"switch", "switch2", "3ds", "ps3", "ps2", "xbox", "xbox360"}:
            strip_w = max(3.0, rect.height() * 0.16)
            painter.fillRect(QRectF(rect.left(), rect.top(), strip_w, rect.height()), accent)

        font = QFont(style.heading_font or UI_FONT)
        font.setPixelSize(max(8, int(rect.height() * 0.42)))
        font.setWeight(QFont.DemiBold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, rect.height() * 0.04)
        painter.setFont(font)
        painter.setPen(QColor(profile.header_text))

        pad = rect.height() * 0.28
        text_rect = QRectF(
            rect.left() + pad, rect.top(), rect.width() - pad * 1.8, rect.height()
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
        profile = item.profile
        color = QColor(profile.header_bg) if profile.key in CASE_PROFILES else _band_color(item.game)
        shade = QLinearGradient(band.topLeft(), band.bottomLeft())
        shade.setColorAt(0.0, color.lighter(110))
        shade.setColorAt(1.0, color.darker(122))
        painter.fillRect(band, QBrush(shade))

        top_line = QColor(profile.header_accent)
        top_line.setAlpha(150)
        painter.setPen(QPen(top_line, 1.0))
        painter.drawLine(QPointF(band.left(), band.top()), QPointF(band.right(), band.top()))

        text = profile.band_label or _band_text(item.game)
        ink = QColor(profile.header_text) if profile.key in CASE_PROFILES else _readable_on(color)
        font = QFont(UI_FONT)
        font.setPixelSize(max(7, int(band.height() * 0.38)))
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
        profile = item.profile
        base_color = QColor(profile.header_bg)
        accent = QColor(profile.header_accent)
        base = QLinearGradient(band.topLeft(), band.bottomLeft())
        base.setColorAt(0.0, _mix(base_color, accent, 0.14))
        base.setColorAt(1.0, _mix(base_color, QColor(active_style().bg), 0.35))
        painter.fillRect(band, QBrush(base))

        hairline = QColor(accent)
        hairline.setAlpha(135)
        painter.setPen(QPen(hairline, 1))
        painter.drawLine(
            QPointF(band.left(), band.top()), QPointF(band.right(), band.top())
        )

        ink = QColor(profile.header_text)
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
        marker.setAlpha(190)
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
        accent = QColor(item.profile.header_accent or style.accent)
        base = QLinearGradient(frame.topLeft(), frame.bottomRight())
        base.setColorAt(0.0, QColor(style.surface_2))
        base.setColorAt(0.55, _mix(accent, QColor(style.bg), 0.84))
        base.setColorAt(1.0, _mix(accent, QColor(style.bg), 0.66))
        painter.fillRect(frame, QBrush(base))

        line = QColor(accent)
        line.setAlpha(36)
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
        text_color.setAlpha(75)
        painter.setPen(text_color)
        painter.drawText(frame, Qt.AlignCenter, initials)

        painter.setPen(QPen(accent, 1))
        painter.setOpacity(0.45)
        line_y = frame.center().y() + frame.height() * 0.14
        painter.drawLine(
            QPointF(frame.center().x() - frame.width() * 0.16, line_y),
            QPointF(frame.center().x() + frame.width() * 0.16, line_y),
        )
        painter.setOpacity(1.0)

    def _paint_stand(
        self,
        painter: QPainter,
        target: QRectF,
        item: ShelfItem,
        geometry: dict,
        selected: bool,
    ) -> None:
        focus = geometry["focus"]
        strength = focus if selected else focus * 0.45
        if strength <= 0.02:
            return
        base_y = target.bottom() + 3
        width = target.width()
        height = target.height()
        accent = item.dominant if selected else QColor(active_style().accent)

        pool = QRadialGradient(target.center().x(), base_y + 4, width * 0.68)
        center = QColor(accent)
        center.setAlpha(int(68 * strength))
        edge = QColor(accent)
        edge.setAlpha(int(20 * strength))
        pool.setColorAt(0.0, center)
        pool.setColorAt(0.55, edge)
        pool.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(pool))
        painter.drawEllipse(
            QPointF(target.center().x(), base_y + 4), width * 0.68, height * 0.036
        )

        shadow = QRadialGradient(target.center().x(), base_y, width * 0.5)
        shadow.setColorAt(0.0, QColor(0, 0, 0, int(170 * max(0.3, strength))))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(
            QPointF(target.center().x(), base_y), width * 0.42, height * 0.022
        )
