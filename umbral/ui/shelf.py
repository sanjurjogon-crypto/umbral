from __future__ import annotations

import math
import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter
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
from .cases import (
    CASE_PROFILES,
    EMULATOR_BY_NAME,
    EMULATOR_COLORS,
    EMULATOR_NAMES,
    PC_BAND,
    PC_BAND_LIGHT,
    CaseProfile,
    _band_color,
    _band_text,
    _emulator_key,
    case_profile,
    is_pc_case,
    paint_console_case,
    paint_console_spine,
)
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

CANVAS_BG = "#070604"
WASH_TOP = "#0c0a07"
WASH_MID = "#090705"
WASH_BOTTOM = "#050403"
HALO_MAIN = QColor(201, 164, 95, 34)
HALO_SOFT = QColor(140, 100, 50, 12)
SPINE_COLOR = QColor(201, 164, 95)
ACCENT_TEXT = "#e7d6ad"

_RAW_COVER_CACHE: OrderedDict[str, tuple[float, QPixmap, QColor]] = OrderedDict()
_ICON_CACHE: dict[str, Optional[QPixmap]] = {}
_SYNTH_ICON_CACHE: dict[tuple[str, str, int], QPixmap] = {}
_is_pc_case = is_pc_case


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


def _cached_cover_data(
    game: Game, fallback: QColor
) -> tuple[Optional[QPixmap], str, QColor]:
    path = game_cover(game)
    if path is None:
        return None, "", QColor(fallback)
    key = str(path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None, "", QColor(fallback)
    entry = _RAW_COVER_CACHE.get(key)
    if entry is not None and entry[0] == mtime:
        _RAW_COVER_CACHE.move_to_end(key)
        return entry[1], key, QColor(entry[2])
    pixmap = QPixmap(key)
    if pixmap.isNull():
        return None, "", QColor(fallback)
    dom = _dominant_color(pixmap, fallback)
    _RAW_COVER_CACHE[key] = (mtime, pixmap, dom)
    if len(_RAW_COVER_CACHE) > 120:
        _RAW_COVER_CACHE.popitem(last=False)
    return pixmap, key, dom


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


def emulator_badge_pixmap(game: Game, size: int = 24) -> Optional[QPixmap]:
    """Return the emulator icon pixmap for display beside the game title below the shelf."""
    sys_key = (game.system_key or "").strip().lower()
    if is_pc_case(game) and sys_key != "ports":
        return None
    pixmap = _exe_badge(game.executable)
    if pixmap is not None and not pixmap.isNull():
        return pixmap
    emu_name = (game.emulator or "").strip()
    if not emu_name:
        return None
    emu_key = _emulator_key(game)
    accent = EMULATOR_COLORS.get(emu_key, game.accent or "#d4af37")
    cache_key = (emu_name.lower(), accent, max(16, size))
    cached = _SYNTH_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached

    dim = max(16, size)
    badge = QPixmap(dim, dim)
    badge.fill(Qt.transparent)
    painter = QPainter(badge)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)

    color = QColor(accent)
    if not color.isValid():
        color = QColor("#d4af37")
    rect = QRectF(1.0, 1.0, dim - 2.0, dim - 2.0)
    fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
    fill.setColorAt(0.0, color.lighter(115))
    fill.setColorAt(1.0, color.darker(145))
    painter.setPen(QPen(color.lighter(150), 1.0))
    painter.setBrush(QBrush(fill))
    painter.drawRoundedRect(rect, dim * 0.28, dim * 0.28)

    words = [w for w in emu_name.replace("-", " ").split() if w]
    monogram = "".join(w[0] for w in words[:2]).upper() if len(words) >= 2 else emu_name[:2].upper()
    font = QFont("Segoe UI")
    font.setPixelSize(max(8, int(dim * 0.44)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(_readable_on(color))
    painter.drawText(rect, Qt.AlignCenter, monogram or "E")
    painter.end()

    _SYNTH_ICON_CACHE[cache_key] = badge
    return badge


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
    turn: float,
    hover_x: float = 0.0,
    hover_y: float = 0.0,
) -> list[QPointF]:
    """Compute a clean 3D-rotated rectangular box quad with smooth continuous turn interpolation."""
    half_w = width / 2.0
    half_h = height / 2.0
    foreshorten = half_w * 0.135 * tilt
    taper = half_h * 0.048 * tilt
    clamped_turn = max(-1.0, min(1.0, float(turn)))
    left_dy = -clamped_turn * taper
    right_dy = clamped_turn * taper
    yaw = hover_x * half_h * 0.030
    pitch = hover_y * half_w * 0.026
    return [
        QPointF(-half_w + foreshorten + pitch, -half_h + left_dy - yaw),
        QPointF(half_w - foreshorten - pitch, -half_h + right_dy + yaw),
        QPointF(half_w - foreshorten + pitch, half_h - right_dy - yaw),
        QPointF(-half_w + foreshorten - pitch, half_h - left_dy + yaw),
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


def _pillow_sharp_cover(
    cover_path: str, pixmap: Optional[QPixmap], target_w: int, target_h: int, center_x: float
) -> Optional[np.ndarray]:
    """Scale the full cover artwork comfortably without over-zooming, feathered over a subtle wide wash."""
    img: Optional[Image.Image] = None
    try:
        if cover_path:
            with Image.open(cover_path) as loaded:
                img = loaded.convert("RGB")
        elif pixmap is not None and not pixmap.isNull():
            qimg = pixmap.toImage().convertToFormat(QImage.Format_RGB888)
            stride = qimg.bytesPerLine()
            raw = bytes(qimg.constBits())
            arr = np.frombuffer(raw, dtype=np.uint8).reshape((qimg.height(), stride))[:, : qimg.width() * 3]
            img = Image.fromarray(arr.reshape((qimg.height(), qimg.width(), 3)), mode="RGB")
    except OSError:
        img = None
    if img is None:
        return None

    src_w, src_h = img.size
    if src_w <= 0 or src_h <= 0:
        return None

    # Soft wide ambient fill underneath so widescreen margins harmonize smoothly
    amb_scale = max(target_w / src_w, target_h / src_h)
    amb_w = max(target_w, int(round(src_w * amb_scale)))
    amb_h = max(target_h, int(round(src_h * amb_scale)))
    amb = img.resize((max(200, amb_w // 4), max(120, amb_h // 4)), Image.Resampling.LANCZOS)
    amb = amb.filter(ImageFilter.GaussianBlur(radius=18)).resize((amb_w, amb_h), Image.Resampling.BILINEAR)
    ax0 = max(0, (amb_w - target_w) // 2)
    ay0 = max(0, (amb_h - target_h) // 3)
    ambient_arr = np.asarray(amb.crop((ax0, ay0, ax0 + target_w, ay0 + target_h)), dtype=np.float32) * 0.45

    # Fit the entire cover artwork comfortably inside the stage so the whole illustration stays visible
    avail_w = max(320.0, float(target_w) * 0.72)
    avail_h = max(240.0, float(target_h) * 0.90)
    fit_scale = min(avail_w / src_w, avail_h / src_h)
    fit_w = max(16, min(target_w, int(round(src_w * fit_scale))))
    fit_h = max(16, min(target_h, int(round(src_h * fit_scale))))
    sharp = img.resize((fit_w, fit_h), Image.Resampling.LANCZOS)
    if fit_scale > 1.04:
        sharp = sharp.filter(ImageFilter.UnsharpMask(radius=1.0, percent=45, threshold=3))
    sharp_arr = np.asarray(sharp, dtype=np.float32)

    cx = int(round(max(fit_w / 2.0, min(target_w - fit_w / 2.0, center_x))))
    cy = int(round(target_h * 0.45))
    x0 = max(0, cx - fit_w // 2)
    y0 = max(0, min(target_h - fit_h, cy - fit_h // 2))
    x1 = min(target_w, x0 + fit_w)
    y1 = min(target_h, y0 + fit_h)
    pw, ph = x1 - x0, y1 - y0
    if pw > 0 and ph > 0:
        ux = np.linspace(0.0, 1.0, pw, dtype=np.float32)[None, :]
        uy = np.linspace(0.0, 1.0, ph, dtype=np.float32)[:, None]
        fx = np.clip(np.minimum(ux, 1.0 - ux) / 0.22, 0.0, 1.0)
        fy = np.clip(np.minimum(uy, 1.0 - uy) / 0.16, 0.0, 1.0)
        # Hermite smoothstep feathering on all 4 sides
        fx = fx * fx * (3.0 - 2.0 * fx)
        fy = fy * fy * (3.0 - 2.0 * fy)
        alpha = (fx * fy)[:, :, None]
        ambient_arr[y0:y1, x0:x1] = (
            ambient_arr[y0:y1, x0:x1] * (1.0 - alpha) + sharp_arr[:ph, :pw] * alpha
        )
    return ambient_arr


def render_debanded_backdrop(
    width: int,
    height: int,
    center_x: float,
    center_y: float,
    cover_w: float,
    cover_h: float,
    cover_path: str,
    pixmap: Optional[QPixmap],
    dominant: QColor,
    halo_enabled: bool,
) -> QPixmap:
    """Render a crisp full-res backdrop with triangular-PDF debanding and subtle film grain."""
    w = max(16, int(width))
    h = max(16, int(height))

    y_norm = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    x_norm = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]

    top_c = QColor(WASH_TOP)
    bottom_c = QColor(WASH_BOTTOM)
    base = np.empty((h, w, 3), dtype=np.float32)
    for ch, (t_v, b_v) in enumerate(
        (
            (top_c.red(), bottom_c.red()),
            (top_c.green(), bottom_c.green()),
            (top_c.blue(), bottom_c.blue()),
        )
    ):
        base[:, :, ch] = t_v + (b_v - t_v) * y_norm[:, 0][:, None]

    cover_arr = _pillow_sharp_cover(cover_path, pixmap, w, h, center_x)
    if cover_arr is not None:
        # Smooth atmospheric blend keeping sharp background artwork clearly visible behind cases
        veil = 0.24 + 0.34 * np.exp(-((y_norm - 0.44) / 0.36) ** 2)
        base = base * (1.0 - veil[:, :, None]) + cover_arr * veil[:, :, None]

    if halo_enabled:
        dom = np.array([dominant.red(), dominant.green(), dominant.blue()], dtype=np.float32)
        cx_n = center_x / w
        cy_n = center_y / h
        rx = max(0.28, (cover_w * 2.15) / w)
        ry = max(0.32, (cover_h * 1.45) / h)
        r2 = ((x_norm - cx_n) / rx) ** 2 + ((y_norm - cy_n) / ry) ** 2
        glow = 0.28 * np.exp(-r2 * 1.35)

        spot_ry = max(0.45, (cover_h * 1.75) / h)
        spot_r2 = ((x_norm - cx_n) / (rx * 0.85)) ** 2 + ((y_norm - 0.14) / spot_ry) ** 2
        spotlight = 0.14 * np.exp(-spot_r2 * 1.55)

        halo_w = np.clip(glow + spotlight, 0.0, 0.45)[:, :, None]
        spot_tint = np.clip(dom * 1.25 + 24.0, 0.0, 255.0)
        base = base * (1.0 - halo_w) + spot_tint[None, None, :] * halo_w

    # Gentle cinematic edge vignette
    vx = (x_norm - 0.5) / 0.56
    vy = (y_norm - 0.46) / 0.58
    vig = 1.0 - 0.42 * np.clip((vx * vx + vy * vy) * 0.55, 0.0, 1.0)
    base *= vig[:, :, None]

    # Triangular-PDF deband dither + subtle monochrome film grain prevents 8-bit color banding rings
    rng = np.random.default_rng(2026)
    u1 = rng.random((h, w), dtype=np.float32)
    u2 = rng.random((h, w), dtype=np.float32)
    grain = (u1 + u2 - 1.0) * 3.1
    base = np.clip(base + grain[:, :, None], 0.0, 255.0).astype(np.uint8)

    qimg = QImage(base.data, w, h, w * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


@dataclass
class ShelfItem:
    game: Game
    pixmap: Optional[QPixmap]
    cover_path: str
    profile: CaseProfile
    dominant: QColor
    front_cache: Optional[QPixmap] = None
    front_cache_key: tuple = ()
    refl_cache: Optional[QPixmap] = None
    refl_cache_key: tuple = ()


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
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

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
        self._inset_left = 0
        self._inset_top = 0
        self._halo_enabled = True
        self._backdrop_mix = 1.0
        self._prev_backdrop_item: Optional[ShelfItem] = None
        self._active_backdrop_id: str = ""
        self._backdrop_cache: OrderedDict[tuple, QPixmap] = OrderedDict()

        self._anim = QPropertyAnimation(self, b"position", self)
        self._anim.setDuration(380)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self._hover_anim = QPropertyAnimation(self, b"hover_lift", self)
        self._hover_anim.setDuration(200)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._bg_anim = QPropertyAnimation(self, b"backdrop_mix", self)
        self._bg_anim.setDuration(360)
        self._bg_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._tilt_timer = QTimer(self)
        self._tilt_timer.setInterval(16)
        self._tilt_timer.timeout.connect(self._step_tilt)

    def set_chrome_insets(self, left: int, top: int) -> None:
        left_val = max(0, int(left))
        top_val = max(0, int(top))
        if (left_val, top_val) == (self._inset_left, self._inset_top):
            return
        self._inset_left = left_val
        self._inset_top = top_val
        self._backdrop_cache.clear()
        self.update()

    def set_halo_enabled(self, enabled: bool) -> None:
        flag = bool(enabled)
        if flag == self._halo_enabled:
            return
        self._halo_enabled = flag
        self._backdrop_cache.clear()
        self.update()

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
            profile = case_profile(game)
            item_fallback = QColor(profile.header_accent or fallback.name())
            pixmap, cover_path, dominant = _cached_cover_data(game, item_fallback)
            items.append(ShelfItem(game, pixmap, cover_path, profile, dominant))
        self.items = items
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
        self._prev_backdrop_item = None
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

    def _start_backdrop_transition(
        self, previous: Optional[ShelfItem], current: Optional[ShelfItem]
    ) -> None:
        cur_id = current.game.id if current is not None else ""
        if cur_id == self._active_backdrop_id:
            return
        self._prev_backdrop_item = previous
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
        old_index = self.index
        new_index = max(0, min(self.index + delta, len(self.items) - 1))
        self.index = new_index
        current_item = self._current_item()
        if new_index != old_index:
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
        usable_w = max(320.0, float(self.width() - self._inset_left))
        usable_h = max(240.0, float(self.height() - self._inset_top))
        center_x = self._inset_left + usable_w / 2.0
        center_y = self._inset_top + usable_h * 0.445
        scale = min(usable_w / 1240.0, 1.18)
        cover_w = CASE_W * max(0.72, scale)
        cover_h = CASE_H * max(0.72, scale)
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
            "turn": max(-1.0, min(1.0, offset)),
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

    def _backdrop_for(
        self,
        item: Optional[ShelfItem],
        center_x: float,
        center_y: float,
        cover_w: float,
        cover_h: float,
    ) -> QPixmap:
        key_id = item.game.id if item is not None else "__none__"
        cov_key = item.cover_path if item is not None else ""
        cache_key = (
            key_id,
            cov_key,
            self.width(),
            self.height(),
            int(center_x),
            int(center_y),
            self._halo_enabled,
        )
        cached = self._backdrop_cache.get(cache_key)
        if cached is not None:
            self._backdrop_cache.move_to_end(cache_key)
            return cached
        fallback = QColor(active_style().accent)
        rendered = render_debanded_backdrop(
            self.width(),
            self.height(),
            center_x,
            center_y,
            cover_w,
            cover_h,
            cov_key,
            item.pixmap if item is not None else None,
            item.dominant if item is not None else fallback,
            self._halo_enabled,
        )
        self._backdrop_cache[cache_key] = rendered
        if len(self._backdrop_cache) > 18:
            self._backdrop_cache.popitem(last=False)
        return rendered

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.fillRect(self.rect(), QColor(CANVAS_BG))

        center_x, center_y, cover_w, cover_h, gap = self._layout()
        current_item = self._current_item()

        self._paint_backdrop(painter, current_item, center_x, center_y, cover_w, cover_h)
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
        if self._prev_backdrop_item is not None and self._backdrop_mix < 1.0:
            return _mix(self._prev_backdrop_item.dominant, target_color, self._backdrop_mix)
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
        mix = _smooth(self._backdrop_mix)
        if self._prev_backdrop_item is not None and mix < 0.99:
            prev_bg = self._backdrop_for(
                self._prev_backdrop_item, center_x, center_y, cover_w, cover_h
            )
            painter.drawPixmap(0, 0, prev_bg)
            cur_bg = self._backdrop_for(current_item, center_x, center_y, cover_w, cover_h)
            painter.save()
            painter.setOpacity(mix)
            painter.drawPixmap(0, 0, cur_bg)
            painter.restore()
            return
        cur_bg = self._backdrop_for(current_item, center_x, center_y, cover_w, cover_h)
        painter.drawPixmap(0, 0, cur_bg)

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
        dominant = self._blended_dominant(current_item) if self._halo_enabled else QColor(active_style().accent)

        floor_rect = QRectF(0, floor_y, rect.width(), max(0.0, rect.bottom() - floor_y))
        marble = QLinearGradient(0, floor_y, 0, rect.bottom())
        tint_alpha = 26 if self._halo_enabled else 10
        marble.setColorAt(0.0, QColor(dominant.red(), dominant.green(), dominant.blue(), tint_alpha))
        marble.setColorAt(0.28, QColor(11, 10, 9, 175))
        marble.setColorAt(1.0, QColor(4, 4, 3, 240))
        painter.fillRect(floor_rect, QBrush(marble))

        sheen = QLinearGradient(0, floor_y, rect.width(), floor_y)
        sheen.setColorAt(0.0, QColor(0, 0, 0, 0))
        sheen.setColorAt(
            0.30,
            QColor(dominant.red(), dominant.green(), dominant.blue(), 42 if self._halo_enabled else 18),
        )
        sheen.setColorAt(0.55, QColor(255, 250, 238, 72))
        sheen.setColorAt(
            0.78,
            QColor(dominant.red(), dominant.green(), dominant.blue(), 42 if self._halo_enabled else 18),
        )
        sheen.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(QPen(QBrush(sheen), 1.2))
        painter.drawLine(QPointF(0, floor_y), QPointF(rect.width(), floor_y))

    def _front_pixmap_for(
        self, item: ShelfItem, base_w: int, base_h: int
    ) -> QPixmap:
        """Render and cache the complete 3D box front design (title, art, console band, badge, border)."""
        style = active_style()
        key = (
            max(48, base_w),
            max(48, base_h),
            item.game.title,
            item.game.favorite,
            item.game.state,
            item.cover_path,
            item.profile.key,
            style.key,
        )
        if item.front_cache is not None and item.front_cache_key == key:
            return item.front_cache

        width = float(key[0])
        height = float(key[1])
        pix = QPixmap(key[0], key[1])
        pix.fill(Qt.transparent)
        buf = QPainter(pix)
        buf.setRenderHint(QPainter.Antialiasing)
        buf.setRenderHint(QPainter.SmoothPixmapTransform)
        buf.setRenderHint(QPainter.TextAntialiasing)

        frame = QRectF(0.0, 0.0, width, height)
        profile = item.profile
        radius = profile.radius

        outer = QPainterPath()
        outer.addRoundedRect(frame, radius, radius)
        buf.setClipPath(outer)

        if profile.shell_kind == "pc_keepcase":
            band_h = height * 0.115
            art = QRectF(0.0, 0.0, width, height - band_h)
            band = QRectF(0.0, height - band_h, width, band_h)

            if item.pixmap is not None and not item.pixmap.isNull():
                src_size = art.size().toSize()
                ratio = item.pixmap.width() / max(1, item.pixmap.height())
                target_ratio = art.width() / max(1.0, art.height())
                if ratio > target_ratio * 1.25:
                    buf.fillRect(art, QColor("#080705"))
                    small = QSize(max(1, int(src_size.width() * 0.14)), max(1, int(src_size.height() * 0.14)))
                    backdrop = item.pixmap.scaled(
                        small, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                    ).scaled(src_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    buf.setOpacity(0.42)
                    buf.drawPixmap(
                        QPointF(art.center().x() - backdrop.width() / 2.0, art.center().y() - backdrop.height() / 2.0),
                        backdrop,
                    )
                    buf.setOpacity(1.0)
                    scaled = item.pixmap.scaled(src_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    buf.drawPixmap(
                        QPointF(art.center().x() - scaled.width() / 2.0, art.center().y() - scaled.height() / 2.0),
                        scaled,
                    )
                else:
                    src = item.pixmap.scaled(src_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    sx = max(0, (src.width() - src_size.width()) // 2)
                    sy = max(0, (src.height() - src_size.height()) // 2)
                    buf.drawPixmap(art.topLeft(), src.copy(sx, sy, src_size.width(), src_size.height()))
            else:
                self._paint_placeholder(buf, art, item)

            self._paint_pc_band(buf, band, item)
            self._paint_status_badges(buf, art, item)

            sheen = QLinearGradient(frame.topLeft(), QPointF(width * 0.6, height * 0.55))
            sheen.setColorAt(0.0, QColor(255, 255, 255, 24))
            sheen.setColorAt(0.45, QColor(255, 255, 255, 8))
            sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
            buf.setPen(Qt.NoPen)
            buf.setBrush(QBrush(sheen))
            buf.drawRoundedRect(frame, radius, radius)

            frame_line = QColor(255, 255, 255, 58)
            buf.setPen(QPen(frame_line, 1.2))
            buf.setBrush(Qt.NoBrush)
            buf.drawRoundedRect(frame.adjusted(0.6, 0.6, -0.6, -0.6), radius, radius)
        else:
            art = paint_console_case(
                buf,
                frame,
                profile,
                item.pixmap,
                lambda painter, rect: self._paint_placeholder(painter, rect, item),
            )
            self._paint_status_badges(buf, art, item)

        buf.end()

        item.front_cache = pix
        item.front_cache_key = key
        return pix

    def _refl_pixmap_for(
        self, item: ShelfItem, base_w: int, base_h: int
    ) -> QPixmap:
        """Build a flipped, softly alpha-faded copy of the complete 3D box front (zero hard bottom cut)."""
        front = self._front_pixmap_for(item, base_w, base_h)
        refl_h = max(32, int(round(front.height() * 0.68)))
        key = (*item.front_cache_key, refl_h)
        if item.refl_cache is not None and item.refl_cache_key == key:
            return item.refl_cache

        flipped_full = front.transformed(QTransform().scale(1.0, -1.0))
        cropped = flipped_full.copy(0, 0, front.width(), min(refl_h, flipped_full.height()))

        out = QPixmap(front.width(), refl_h)
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.drawPixmap(0, 0, cropped)
        # Smooth continuous alpha mask fading completely to 0 before the bottom edge
        mask = QLinearGradient(0, 0, 0, refl_h)
        mask.setColorAt(0.0, QColor(0, 0, 0, 195))
        mask.setColorAt(0.28, QColor(0, 0, 0, 110))
        mask.setColorAt(0.68, QColor(0, 0, 0, 28))
        mask.setColorAt(0.92, QColor(0, 0, 0, 0))
        mask.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p.fillRect(0, 0, out.width(), refl_h, QBrush(mask))
        p.end()

        item.refl_cache = out
        item.refl_cache_key = key
        return out

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
        strength = max(0.42, focus) * (1.0 - min(0.55, geometry["dim"] * 0.65))
        if strength <= 0.08:
            return
        target = self._case_rect(item, geometry, center_x, center_y, cover_w, cover_h)
        turn = float(geometry.get("turn", 0.0))
        tilt_amount = (1.0 - focus) * 0.85 + 0.12
        hover_x = self._tilt_x * focus if selected else 0.0
        hover_y = self._tilt_y * focus if selected else 0.0
        quad = _perspective_quad(
            target.width(), target.height(), tilt_amount, turn, hover_x=hover_x, hover_y=hover_y
        )

        # Anchor flipped 3D reflection directly under the bottom perspective edge of the case
        bl = QPointF(target.center().x() + quad[3].x(), target.center().y() + quad[3].y() + 2.0)
        br = QPointF(target.center().x() + quad[2].x(), target.center().y() + quad[2].y() + 2.0)
        refl_h = target.height() * 0.68
        l_drop = refl_h + (quad[3].y() - quad[2].y()) * 0.35
        r_drop = refl_h + (quad[2].y() - quad[3].y()) * 0.35
        refl_quad = [
            bl,
            br,
            QPointF(br.x(), br.y() + r_drop),
            QPointF(bl.x(), bl.y() + l_drop),
        ]
        refl_rect = QRectF(target.left(), target.bottom() + 2.0, target.width(), refl_h)
        source = [
            QPointF(refl_rect.left(), refl_rect.top()),
            QPointF(refl_rect.right(), refl_rect.top()),
            QPointF(refl_rect.right(), refl_rect.bottom()),
            QPointF(refl_rect.left(), refl_rect.bottom()),
        ]
        trans = _quad_transform(source, refl_quad)

        base_w = max(48, int(round(cover_w * item.profile.w_scale)))
        base_h = max(48, int(round(cover_h * item.profile.h_scale)))
        refl_pix = self._refl_pixmap_for(item, base_w, base_h)

        painter.save()
        painter.setTransform(trans, False)
        painter.setOpacity(0.56 * strength if selected else 0.44 * strength)
        # Mirror both left & right 3D spines continuously into floor
        max_depth = CASE_DEPTH * (target.width() / CASE_W) * 0.55 * item.profile.depth_scale
        left_depth = max_depth * (0.28 + 0.72 * max(0.0, turn))
        right_depth = max_depth * (0.28 + 0.72 * max(0.0, -turn))
        spine_grad = QLinearGradient(0, refl_rect.top(), 0, refl_rect.bottom())
        spine_base = QColor(item.profile.spine_color)
        spine_grad.setColorAt(0.0, QColor(spine_base.red(), spine_base.green(), spine_base.blue(), 170))
        spine_grad.setColorAt(0.7, QColor(spine_base.red(), spine_base.green(), spine_base.blue(), 35))
        spine_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)

        left_spine = QPainterPath()
        left_spine.moveTo(refl_rect.left(), refl_rect.top())
        left_spine.lineTo(refl_rect.left() - left_depth, refl_rect.top() - left_depth * 0.32)
        left_spine.lineTo(refl_rect.left() - left_depth, refl_rect.bottom())
        left_spine.lineTo(refl_rect.left(), refl_rect.bottom())
        left_spine.closeSubpath()
        painter.fillPath(left_spine, QBrush(spine_grad))

        right_spine = QPainterPath()
        right_spine.moveTo(refl_rect.right(), refl_rect.top())
        right_spine.lineTo(refl_rect.right() + right_depth, refl_rect.top() - right_depth * 0.32)
        right_spine.lineTo(refl_rect.right() + right_depth, refl_rect.bottom())
        right_spine.lineTo(refl_rect.right(), refl_rect.bottom())
        right_spine.closeSubpath()
        painter.fillPath(right_spine, QBrush(spine_grad))

        painter.drawPixmap(refl_rect, refl_pix, QRectF(refl_pix.rect()))
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
        turn = float(geometry.get("turn", 0.0))
        tilt_amount = (1.0 - geometry["focus"]) * 0.85 + 0.12
        hover_x = self._tilt_x * geometry["focus"] if selected else 0.0
        hover_y = self._tilt_y * geometry["focus"] if selected else 0.0

        quad = _perspective_quad(
            target.width(), target.height(), tilt_amount, turn, hover_x=hover_x, hover_y=hover_y
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
        self._paint_spine(painter, target, item, turn)
        self._paint_front(painter, target, item, selected, geometry["focus"], cover_w, cover_h)
        painter.restore()

        fade = min(0.74, geometry["dim"] * 0.92)
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

    def _paint_spine(
        self, painter: QPainter, target: QRectF, item: ShelfItem, turn: float = 0.0
    ) -> None:
        """Paint 3D side spines on both edges continuously matching real shell physics."""
        paint_console_spine(painter, target, item.profile, turn)

    def _paint_front(
        self,
        painter: QPainter,
        target: QRectF,
        item: ShelfItem,
        selected: bool,
        focus: float,
        cover_w: float,
        cover_h: float,
    ) -> None:
        frame = QRectF(target)
        width = frame.width()
        profile = item.profile
        radius = profile.radius

        base_w = max(48, int(round(cover_w * profile.w_scale)))
        base_h = max(48, int(round(cover_h * profile.h_scale)))
        front = self._front_pixmap_for(item, base_w, base_h)

        painter.save()
        outer = QPainterPath()
        outer.addRoundedRect(frame, radius, radius)
        painter.setClipPath(outer)
        painter.drawPixmap(frame, front, QRectF(front.rect()))

        # Subtle interactive specular highlight shifting with cursor tilt (softer on matte cardboard)
        sheen_shift = (self._tilt_x * 0.32 if selected else 0.0) * focus
        sheen = QLinearGradient(
            QPointF(frame.left() + width * (0.15 + sheen_shift), frame.top()),
            QPointF(frame.left() + width * (0.75 + sheen_shift), frame.bottom()),
        )
        base_sheen = (38 if selected else 18) + abs(self._tilt_x) * 24 * focus
        if profile.shell_kind == "cardboard":
            base_sheen *= 0.30
        elif profile.shell_kind in {"translucent_clear", "jewel_clear"}:
            base_sheen *= 1.15
        peak_alpha = int(min(90.0, base_sheen))
        sheen.setColorAt(0.0, QColor(255, 248, 232, 0))
        sheen.setColorAt(0.32, QColor(255, 248, 232, peak_alpha))
        sheen.setColorAt(0.50, QColor(255, 255, 255, int(peak_alpha * 0.42)))
        sheen.setColorAt(0.75, QColor(0, 0, 0, 10))
        sheen.setColorAt(1.0, QColor(0, 0, 0, 34))
        painter.fillRect(frame, QBrush(sheen))
        painter.restore()

        if selected:
            glow = QColor(item.dominant) if self._halo_enabled else QColor(active_style().accent)
            glow.setAlpha(155 if self._halo_enabled else 105)
            painter.setPen(QPen(glow, 1.6))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(frame.adjusted(-1.2, -1.2, 1.2, 1.2), radius + 1.0, radius + 1.0)

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
            name = "PC"

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
        base_y = target.bottom() + 2
        width = target.width()
        height = target.height()

        if self._halo_enabled:
            accent = item.dominant if selected else QColor(active_style().accent)
            pool = QRadialGradient(target.center().x(), base_y + 4, width * 0.68)
            center = QColor(accent)
            center.setAlpha(int(58 * strength))
            edge = QColor(accent)
            edge.setAlpha(int(16 * strength))
            pool.setColorAt(0.0, center)
            pool.setColorAt(0.55, edge)
            pool.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(pool))
            painter.drawEllipse(
                QPointF(target.center().x(), base_y + 4), width * 0.68, height * 0.036
            )

        shadow = QRadialGradient(target.center().x(), base_y, width * 0.52)
        shadow.setColorAt(0.0, QColor(0, 0, 0, int(175 * max(0.35, strength))))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(
            QPointF(target.center().x(), base_y), width * 0.44, height * 0.024
        )
