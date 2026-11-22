from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)

from ..paths import assets_dir
from .style import GameStyle

_IMAGE_CACHE: dict[tuple[str, int, int], QPixmap | None] = {}


def _scene_image(style: GameStyle, size: QSize) -> QPixmap | None:
    key = (style.key, size.width(), size.height())
    if key in _IMAGE_CACHE:
        return _IMAGE_CACHE[key]
    theme = assets_dir() / "themes" / f"{style.key}.jpg"
    legacy = assets_dir() / "scenes" / f"{style.key}.jpg"
    path = theme if theme.exists() else legacy
    pixmap: QPixmap | None = None
    if path.exists():
        source = QPixmap(str(path))
        if not source.isNull():
            small = source.scaled(
                max(1, size.width() // 10),
                max(1, size.height() // 10),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            pixmap = small.scaled(
                size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
    _IMAGE_CACHE[key] = pixmap
    return pixmap


def clear_image_cache() -> None:
    _IMAGE_CACHE.clear()



def _tint(color: str, alpha: int) -> QColor:
    value = QColor(color)
    value.setAlpha(max(0, min(255, alpha)))
    return value


def _ink(style: GameStyle, alpha: int) -> QColor:
    return _tint(style.text, alpha)


def _shape(painter: QPainter, path: QPainterPath, color: QColor) -> None:
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawPath(path)


def paint_scene(
    painter: QPainter,
    rect: QRectF,
    center_x: float,
    center_y: float,
    cover_w: float,
    cover_h: float,
    style: GameStyle,
) -> None:
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    gold = QColor(style.accent)
    halo = QRadialGradient(center_x, center_y, max(cover_w, cover_h) * 1.6)
    inner = QColor(gold.red(), gold.green(), gold.blue(), 20)
    mid = QColor(gold.red(), gold.green(), gold.blue(), 7)
    halo.setColorAt(0.0, inner)
    halo.setColorAt(0.55, mid)
    halo.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(halo))
    painter.drawEllipse(QPointF(center_x, center_y), cover_w * 1.6, cover_h * 1.4)
    painter.restore()


def _paint_image_scene(
    painter: QPainter, rect: QRectF, image: QPixmap, style: GameStyle
) -> None:
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.drawPixmap(rect.topLeft(), image)

    dark = _dark(style)
    veil = QColor(style.bg)
    veil.setAlpha(110 if dark else 85)
    painter.fillRect(rect, veil)

    accent = QColor(style.accent)
    tint = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    tint.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 26 if dark else 20))
    tint.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.fillRect(rect, QBrush(tint))

    vignette = QRadialGradient(
        rect.center().x(),
        rect.height() * 0.45,
        max(rect.width(), rect.height()) * 0.62,
    )
    vignette.setColorAt(0.45, QColor(0, 0, 0, 0))
    vignette.setColorAt(1.0, QColor(0, 0, 0, 190 if dark else 120))
    painter.fillRect(rect, QBrush(vignette))

    _paint_ornaments(painter, rect, style, dark)


def _paint_ornaments(painter: QPainter, rect: QRectF, style: GameStyle, dark: bool) -> None:
    accent = QColor(style.accent)
    edge = QRectF(rect.left() + 16, rect.top() + 16, rect.width() - 32, rect.height() - 32)
    line = QColor(accent)
    line.setAlpha(150 if dark else 170)
    painter.setPen(QPen(line, 2.0))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(edge)

    inner = edge.adjusted(8, 8, -8, -8)
    soft = QColor(accent)
    soft.setAlpha(70 if dark else 90)
    painter.setPen(QPen(soft, 1.0))
    painter.drawRect(inner)

    corner = min(64.0, rect.width() * 0.065)
    bright = QColor(accent)
    bright.setAlpha(220 if dark else 230)
    for x, y, dx, dy in (
        (edge.left(), edge.top(), 1, 1),
        (edge.right(), edge.top(), -1, 1),
        (edge.left(), edge.bottom(), 1, -1),
        (edge.right(), edge.bottom(), -1, -1),
    ):
        painter.setPen(QPen(bright, 2.4))
        painter.drawLine(QPointF(x, y), QPointF(x + dx * corner, y))
        painter.drawLine(QPointF(x, y), QPointF(x, y + dy * corner))
        painter.setPen(QPen(soft, 1.4))
        painter.drawLine(
            QPointF(x + dx * 12, y + dy * 12),
            QPointF(x + dx * (corner - 16), y + dy * 12),
        )
        center = QPointF(x + dx * 26, y + dy * 26)
        size = 6.0
        diamond = QPainterPath()
        diamond.moveTo(center.x(), center.y() - size)
        diamond.lineTo(center.x() + size, center.y())
        diamond.lineTo(center.x(), center.y() + size)
        diamond.lineTo(center.x() - size, center.y())
        diamond.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(accent.red(), accent.green(), accent.blue(), 220)))
        painter.drawPath(diamond)

    seal_radius = max(34.0, min(rect.width(), rect.height()) * 0.07)
    seal = QPointF(rect.right() - 96, rect.bottom() - 96)
    painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 190), 2.0))
    painter.setBrush(QBrush(QColor(style.bg).darker(118)))
    painter.drawEllipse(seal, seal_radius, seal_radius)
    painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 120), 1.2))
    painter.drawEllipse(seal, seal_radius - 6, seal_radius - 6)

    font = QFont(style.heading_font)
    font.setPixelSize(max(15, int(seal_radius * 0.6)))
    font.setWeight(QFont.DemiBold)
    painter.setFont(font)
    painter.setPen(QColor(style.accent_2))
    initials = "".join(word[0] for word in style.game.split() if word[:1].isalpha())[:3].upper()
    painter.drawText(
        QRectF(seal.x() - seal_radius, seal.y() - seal_radius, seal_radius * 2, seal_radius * 2),
        Qt.AlignCenter,
        initials,
    )

    label_font = QFont(style.heading_font)
    label_font.setPixelSize(12)
    label_font.setLetterSpacing(QFont.AbsoluteSpacing, 4)
    painter.setFont(label_font)
    painter.setPen(QColor(accent.red(), accent.green(), accent.blue(), 200))
    painter.drawText(
        QRectF(rect.left() + 64, rect.bottom() - 52, rect.width() * 0.5, 24),
        Qt.AlignLeft | Qt.AlignVCenter,
        style.game.upper(),
    )


def _dark(style: GameStyle) -> bool:
    value = QColor(style.bg)
    return (0.299 * value.red() + 0.587 * value.green() + 0.114 * value.blue()) < 128


def _souls(painter, rect, cx, cy, cw, ch, style) -> None:
    aura = QRadialGradient(cx, cy, cw * 1.5)
    aura.setColorAt(0.0, _tint("#6b1f0c", 60))
    aura.setColorAt(0.6, _tint("#2a0d05", 22))
    aura.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(aura))
    painter.drawEllipse(QPointF(cx, cy), cw * 1.5, ch * 1.05)

    ring_radius = cw * 1.02
    for index in range(64):
        angle = math.tau * index / 64
        wobble = 0.82 + 0.18 * math.sin(index * 2.3) + 0.06 * math.sin(index * 5.1)
        inner = ring_radius * 0.9
        outer = ring_radius * (1.0 + 0.22 * wobble)
        half = (math.tau / 64) * 0.62
        tip = QPointF(cx + math.cos(angle) * outer, cy + math.sin(angle) * outer)
        left = QPointF(
            cx + math.cos(angle - half) * inner,
            cy + math.sin(angle - half) * inner,
        )
        right = QPointF(
            cx + math.cos(angle + half) * inner,
            cy + math.sin(angle + half) * inner,
        )
        path = QPainterPath(tip)
        path.lineTo(left)
        path.lineTo(right)
        path.closeSubpath()
        warm = (index % 3) / 2.0
        color = QColor(
            int(120 + 95 * warm),
            int(46 + 42 * warm),
            int(16 + 10 * warm),
            120,
        )
        _shape(painter, path, color)

    painter.setPen(QPen(_tint("#c06a2a", 120), max(1.5, cw * 0.01)))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QPointF(cx, cy), ring_radius * 0.82, ring_radius * 0.82)
    painter.setPen(QPen(_tint("#8a3a14", 90), max(1.0, cw * 0.006)))
    painter.drawEllipse(QPointF(cx, cy), ring_radius * 0.68, ring_radius * 0.68)

    spiral = QPainterPath()
    for step in range(90):
        t = step / 89.0
        angle = t * math.tau * 1.4
        radius = ring_radius * (0.22 + 0.46 * t)
        point = QPointF(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)
        if step == 0:
            spiral.moveTo(point)
        else:
            spiral.lineTo(point)
    painter.setPen(QPen(_tint("#e08a3a", 70), max(1.0, cw * 0.006)))
    painter.drawPath(spiral)

    ground_y = cy + ch * 0.62
    ox = max(rect.left() + cw * 0.7, cx - cw * 1.8)
    scale = cw * 0.0125
    painter.save()
    painter.translate(ox, ground_y)
    painter.scale(scale, scale)

    plate = QColor(112, 108, 96, 165)
    dark_plate = QColor(52, 48, 40, 190)
    trim = QColor(160, 132, 78, 150)

    torso = QPainterPath()
    torso.addRoundedRect(QRectF(-34, -9, 58, 20), 9, 9)
    _shape(painter, torso, plate)
    painter.setPen(QPen(dark_plate, 2.2))
    painter.drawArc(QRectF(-30, -7, 26, 16), 200 * 16, 160 * 16)
    painter.setPen(Qt.NoPen)
    for index in range(3):
        x = -22 + index * 9
        painter.setBrush(QBrush(dark_plate))
        painter.drawRoundedRect(QRectF(x, -4, 6, 10), 2, 2)

    for start, end in (((20, -4), (46, -6)), ((20, 4), (48, 8))):
        painter.setPen(QPen(plate, 7, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(*start), QPointF(*end))
        painter.setPen(QPen(dark_plate, 2))
        painter.drawLine(QPointF(*start), QPointF(*end))

    painter.setPen(QPen(plate, 7, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(-28, 0), QPointF(-12, -12))
    painter.setPen(QPen(dark_plate, 2))
    painter.drawLine(QPointF(-28, 0), QPointF(-12, -12))

    helmet = QPainterPath()
    helmet.addEllipse(QRectF(-52, -10, 20, 20))
    _shape(painter, helmet, QColor(132, 128, 116, 190))
    painter.setPen(QPen(dark_plate, 2.4))
    painter.drawLine(QPointF(-54, -2), QPointF(-34, -2))
    painter.drawLine(QPointF(-44, -10), QPointF(-44, 6))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(24, 22, 18, 210)))
    painter.drawRect(QRectF(-50, -3, 12, 3))

    shield_path = QPainterPath()
    shield_path.addEllipse(QRectF(-4, -38, 36, 36))
    _shape(painter, shield_path, QColor(74, 58, 38, 200))
    painter.setPen(QPen(trim, 2.2))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(-3, -37, 34, 34))
    painter.drawLine(QPointF(14, -34), QPointF(14, -6))
    painter.drawLine(QPointF(-2, -20), QPointF(30, -20))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(trim))
    painter.drawEllipse(QPointF(14, -20), 4, 4)

    sword = QPainterPath()
    sword.moveTo(-18, 6)
    sword.lineTo(42, 24)
    sword.lineTo(45, 19)
    sword.lineTo(-15, 2)
    sword.closeSubpath()
    _shape(painter, sword, QColor(150, 146, 134, 175))
    painter.setPen(QPen(QColor(96, 92, 82, 190), 2))
    painter.drawLine(QPointF(-19, 0), QPointF(-9, 10))
    painter.drawLine(QPointF(-15, 4), QPointF(-23, -1))
    painter.restore()

    painter.setPen(Qt.NoPen)
    for index in range(14):
        x = ox - cw * 0.5 + index * cw * 0.08
        y = ground_y + ch * 0.02 + math.sin(index * 1.7) * ch * 0.02
        ember = QColor(190, 90, 30, 70)
        painter.setBrush(QBrush(ember))
        painter.drawEllipse(QPointF(x, y), cw * 0.012, cw * 0.012)


def _zelda(painter, rect, cx, cy, cw, ch, style) -> None:
    tx = cx + cw * 1.55
    ty = cy - ch * 0.52
    size = cw * 0.3
    height = size * 0.866
    centers = (
        (tx, ty - height * 0.52),
        (tx - size * 0.5, ty + height * 0.5),
        (tx + size * 0.5, ty + height * 0.5),
    )
    for px, py in centers:
        top = QPointF(px, py - height * 2.0 / 3.0)
        left = QPointF(px - size * 0.5, py + height / 3.0)
        right = QPointF(px + size * 0.5, py + height / 3.0)
        path = QPainterPath(top)
        path.lineTo(left)
        path.lineTo(right)
        path.closeSubpath()
        _shape(painter, path, _tint("#e3c25a", 150))
    glow = QRadialGradient(tx, ty, size * 1.6)
    glow.setColorAt(0.0, QColor(227, 194, 90, 46))
    glow.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(glow))
    painter.drawEllipse(QPointF(tx, ty), size * 1.6, size * 1.6)

    ox = max(rect.left() + cw * 0.6, cx - cw * 1.8)
    oy = cy + ch * 0.42
    body = QPainterPath()
    body.addEllipse(QRectF(ox - cw * 0.3, oy - ch * 0.12, cw * 0.6, ch * 0.2))
    _shape(painter, body, _tint("#3f7a4e", 150))
    painter.setPen(QPen(_tint("#2c5c39", 170), max(1.2, cw * 0.009)))
    for index in range(6):
        angle = math.pi * (0.15 + 0.7 * index / 5.0)
        start = QPointF(ox + math.cos(angle) * cw * 0.22, oy + ch * 0.02)
        end = QPointF(
            ox + math.cos(angle) * cw * 0.42,
            oy + ch * 0.02 + math.sin(angle) * ch * 0.18,
        )
        painter.drawLine(start, end)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(_tint("#e7e0c4", 190)))
    painter.drawEllipse(QPointF(ox - cw * 0.1, oy - ch * 0.05), cw * 0.035, cw * 0.035)
    painter.drawEllipse(QPointF(ox + cw * 0.1, oy - ch * 0.05), cw * 0.035, cw * 0.035)
    painter.setBrush(QBrush(_tint("#1d2a1a", 220)))
    painter.drawEllipse(QPointF(ox - cw * 0.1, oy - ch * 0.05), cw * 0.014, cw * 0.014)
    painter.drawEllipse(QPointF(ox + cw * 0.1, oy - ch * 0.05), cw * 0.014, cw * 0.014)

    painter.setPen(QPen(_tint("#5d9b62", 90), max(1.0, cw * 0.006)))
    base_y = cy + ch * 0.66
    for index in range(26):
        x = rect.left() + rect.width() * (index + 0.5) / 26.0
        height = ch * (0.04 + 0.03 * math.sin(index * 2.1))
        painter.drawLine(QPointF(x, base_y), QPointF(x + cw * 0.01, base_y - height))


def _elden(painter, rect, cx, cy, cw, ch, style) -> None:
    halo = QRadialGradient(cx, cy - ch * 0.35, cw * 1.4)
    halo.setColorAt(0.0, QColor(227, 193, 101, 34))
    halo.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(halo))
    painter.drawEllipse(QPointF(cx, cy - ch * 0.35), cw * 1.4, ch * 0.85)

    trunk = QPainterPath()
    base_y = cy + ch * 0.7
    top_y = cy - ch * 0.95
    trunk.moveTo(cx - cw * 0.05, base_y)
    trunk.cubicTo(
        cx - cw * 0.08, cy,
        cx - cw * 0.02, cy - ch * 0.4,
        cx - cw * 0.03, top_y,
    )
    trunk.lineTo(cx + cw * 0.03, top_y)
    trunk.cubicTo(
        cx + cw * 0.03, cy - ch * 0.4,
        cx + cw * 0.09, cy,
        cx + cw * 0.05, base_y,
    )
    trunk.closeSubpath()
    _shape(painter, trunk, _tint("#8c6a2a", 80))

    painter.setPen(QPen(_tint("#c9a45f", 90), max(1.4, cw * 0.009)))
    for side in (-1, 1):
        for index in range(5):
            start = QPointF(cx + side * cw * 0.03, cy - ch * 0.35 + index * ch * 0.09)
            end = QPointF(
                cx + side * cw * (0.35 + 0.1 * index),
                start.y() - ch * (0.18 + 0.03 * index),
            )
            painter.drawLine(start, end)
            painter.drawLine(
                end,
                QPointF(end.x() + side * cw * 0.06, end.y() - ch * 0.09),
            )
    painter.setPen(QPen(_tint("#a8832f", 70), max(1.0, cw * 0.007)))
    for index in range(9):
        x = cx + (index - 4) * cw * 0.1
        spread = 0.06 * (4 - abs(index - 4)) + 0.02
        painter.drawLine(
            QPointF(cx, base_y - ch * 0.02),
            QPointF(x + cw * spread, base_y + ch * 0.09),
        )
    painter.setPen(Qt.NoPen)
    input_glow = _tint("#f0d17a", 70)
    painter.setBrush(QBrush(input_glow))
    for index in range(18):
        angle = math.tau * index / 18
        radius = cw * (0.9 + 0.12 * math.sin(index * 2.7))
        x = cx + math.cos(angle) * radius
        y = cy - ch * 0.45 + math.sin(angle) * radius * 0.55
        painter.drawEllipse(QPointF(x, y), cw * 0.008, cw * 0.008)


def _metro(painter, rect, cx, cy, cw, ch, style) -> None:
    painter.setPen(QPen(_tint("#cfc07a", 26), max(1.0, cw * 0.008)))
    for offset in (-1.2, -0.5, 0.5, 1.2):
        x = cx + offset * cw * 0.9
        painter.drawLine(QPointF(x, rect.top()), QPointF(cx + offset * cw * 0.35, cy + ch * 0.7))
    painter.setPen(QPen(_tint("#7b7a64", 90), max(1.2, cw * 0.008)))
    rail_y = cy + ch * 0.62
    painter.drawLine(QPointF(cx - cw * 1.6, rail_y), QPointF(cx + cw * 1.6, rail_y))
    painter.drawLine(QPointF(cx - cw * 1.6, rail_y + ch * 0.05), QPointF(cx + cw * 1.6, rail_y + ch * 0.05))
    for index in range(9):
        x = cx - cw * 1.5 + index * cw * 0.38
        painter.drawLine(QPointF(x, rail_y), QPointF(x, rail_y + ch * 0.05))

    mx = max(rect.left() + cw * 0.8, cx - cw * 1.75)
    my = cy - ch * 0.08
    mask = QPainterPath()
    mask.addEllipse(QRectF(mx - cw * 0.42, my - ch * 0.5, cw * 0.84, ch * 0.7))
    _shape(painter, mask, _tint("#55584a", 150))
    painter.setPen(QPen(_tint("#33362d", 190), max(1.2, cw * 0.008)))
    painter.drawEllipse(QRectF(mx - cw * 0.31, my - ch * 0.36, cw * 0.24, ch * 0.22))
    painter.drawEllipse(QRectF(mx + cw * 0.07, my - ch * 0.36, cw * 0.24, ch * 0.22))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(_tint("#c9a45f", 80)))
    painter.drawEllipse(QRectF(mx - cw * 0.29, my - ch * 0.345, cw * 0.2, ch * 0.19))
    painter.drawEllipse(QRectF(mx + cw * 0.09, my - ch * 0.345, cw * 0.2, ch * 0.19))
    filter = QPainterPath()
    filter.addEllipse(QRectF(mx - cw * 0.17, my + ch * 0.06, cw * 0.34, ch * 0.2))
    _shape(painter, filter, _tint("#3b3d33", 190))
    painter.setPen(QPen(_tint("#22241d", 200), max(1.0, cw * 0.006)))
    for index in range(4):
        y = my + ch * (0.1 + index * 0.035)
        painter.drawLine(QPointF(mx - cw * 0.12, y), QPointF(mx + cw * 0.12, y))
    painter.setPen(QPen(_tint("#454839", 170), max(1.4, cw * 0.01)))
    painter.drawLine(QPointF(mx - cw * 0.42, my - ch * 0.1), QPointF(mx - cw * 0.62, my + ch * 0.05))
    painter.drawLine(QPointF(mx + cw * 0.42, my - ch * 0.1), QPointF(mx + cw * 0.62, my + ch * 0.05))
    painter.setPen(Qt.NoPen)
    spark = QRadialGradient(mx, my - ch * 0.1, cw * 0.5)
    spark.setColorAt(0.0, QColor(220, 200, 120, 40))
    spark.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setBrush(QBrush(spark))
    painter.drawEllipse(QPointF(mx, my - ch * 0.1), cw * 0.5, cw * 0.5)


def _layton(painter, rect, cx, cy, cw, ch, style) -> None:
    ink = _tint("#2f5d8a", 150)
    paper = _tint("#ffffff", 60)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(paper))
    puzzle = QRectF(cx + cw * 1.15, cy - ch * 0.5, cw * 0.55, ch * 0.4)
    painter.drawRoundedRect(puzzle, cw * 0.03, cw * 0.03)
    painter.setBrush(QBrush(ink))
    painter.drawEllipse(
        QPointF(puzzle.center().x(), puzzle.top()), cw * 0.07, cw * 0.07
    )
    painter.setPen(QPen(ink, max(1.2, cw * 0.008)))
    painter.drawLine(
        QPointF(puzzle.left(), puzzle.top() + ch * 0.14),
        QPointF(puzzle.right(), puzzle.top() + ch * 0.14),
    )
    painter.drawLine(
        QPointF(puzzle.left(), puzzle.top() + ch * 0.27),
        QPointF(puzzle.right() - cw * 0.12, puzzle.top() + ch * 0.27),
    )
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(ink))
    font = QFont(style.heading_font)
    font.setPixelSize(int(cw * 0.2))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(47, 93, 138, 170))
    painter.drawText(puzzle, Qt.AlignCenter, "?")

    hx = max(rect.left() + cw * 0.85, cx - cw * 1.75)
    hy = cy - ch * 0.18
    hat = QPainterPath()
    hat.addRect(QRectF(hx - cw * 0.26, hy - ch * 0.34, cw * 0.52, ch * 0.32))
    _shape(painter, hat, _tint("#2b2b33", 190))
    brim = QPainterPath()
    brim.addEllipse(QRectF(hx - cw * 0.44, hy - ch * 0.05, cw * 0.88, ch * 0.12))
    _shape(painter, brim, _tint("#2b2b33", 190))
    painter.setPen(QPen(_tint("#c0703b", 180), max(1.2, cw * 0.008)))
    painter.drawLine(
        QPointF(hx - cw * 0.26, hy - ch * 0.1),
        QPointF(hx + cw * 0.26, hy - ch * 0.1),
    )

    tx = cx + cw * 1.5
    ty = cy + ch * 0.34
    cup = QPainterPath()
    cup.addRoundedRect(QRectF(tx - cw * 0.2, ty - ch * 0.12, cw * 0.4, ch * 0.24), cw * 0.02, cw * 0.02)
    _shape(painter, cup, _tint("#f4f1e6", 210))
    painter.setPen(QPen(_tint("#2f5d8a", 150), max(1.2, cw * 0.008)))
    painter.drawArc(QRectF(tx + cw * 0.17, ty - ch * 0.07, cw * 0.18, ch * 0.14), -80 * 16, 160 * 16)
    saucer = QPainterPath()
    saucer.addEllipse(QRectF(tx - cw * 0.3, ty + ch * 0.1, cw * 0.6, ch * 0.08))
    _shape(painter, saucer, _tint("#e9e4d2", 220))
    painter.setPen(QPen(QColor(120, 110, 90, 90), max(1.0, cw * 0.005)))
    for index in range(3):
        x = tx - cw * 0.1 + index * cw * 0.1
        painter.drawArc(QRectF(x, ty - ch * 0.26, cw * 0.1, ch * 0.16), 0, 180 * 16)


def _tlou(painter, rect, cx, cy, cw, ch, style) -> None:
    silhouette = _tint("#4a5236", 90)
    builder = QPainterPath()
    left = rect.left() + cw * 0.15
    builder.addRect(QRectF(left, cy - ch * 0.55, cw * 0.55, ch * 0.95))
    builder.addRect(QRectF(left + cw * 0.12, cy - ch * 0.7, cw * 0.4, ch * 0.18))
    _shape(painter, builder, silhouette)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(_tint("#2b3122", 120)))
    for row in range(4):
        for column in range(3):
            window = QRectF(
                left + cw * (0.07 + column * 0.16),
                cy - ch * (0.45 - row * 0.17),
                cw * 0.08,
                ch * 0.1,
            )
            painter.drawRect(window)

    gx = cx + cw * 1.6
    gy = cy + ch * 0.15
    painter.setPen(QPen(_tint("#c9b26a", 130), max(1.6, cw * 0.012)))
    painter.drawLine(QPointF(gx, gy), QPointF(gx - cw * 0.1, gy - ch * 0.5))
    painter.drawLine(QPointF(gx - cw * 0.1, gy - ch * 0.5), QPointF(gx - cw * 0.14, gy - ch * 0.78))
    head = QPainterPath()
    head.addEllipse(QRectF(gx - cw * 0.2, gy - ch * 0.86, cw * 0.18, ch * 0.12))
    _shape(painter, head, _tint("#c9b26a", 130))
    painter.setPen(QPen(_tint("#c9b26a", 120), max(1.4, cw * 0.01)))
    painter.drawLine(QPointF(gx, gy), QPointF(gx + cw * 0.04, gy + ch * 0.16))
    painter.drawLine(QPointF(gx - cw * 0.1, gy - ch * 0.5), QPointF(gx - cw * 0.16, gy + ch * 0.18))
    painter.drawLine(QPointF(gx - cw * 0.18, gy - ch * 0.82), QPointF(gx - cw * 0.24, gy - ch * 0.88))
    painter.drawLine(QPointF(gx - cw * 0.18, gy - ch * 0.82), QPointF(gx - cw * 0.2, gy - ch * 0.92))

    painter.setPen(QPen(_tint("#5f7a43", 90), max(1.0, cw * 0.006)))
    for index in range(16):
        x = left + cw * 0.55 + index * cw * 0.06
        height = ch * (0.05 + 0.04 * math.sin(index * 1.9))
        painter.drawLine(QPointF(x, cy + ch * 0.4), QPointF(x + cw * 0.01, cy + ch * 0.4 - height))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(_tint("#d8e27a", 120)))
    painter.drawEllipse(QPointF(left + cw * 0.3, cy - ch * 0.15), cw * 0.012, cw * 0.012)


def _mario(painter, rect, cx, cy, cw, ch, style) -> None:
    px = max(rect.left() + cw * 0.65, cx - cw * 1.85)
    py = cy + ch * 0.66
    pipe = QPainterPath()
    pipe.addRect(QRectF(px - cw * 0.22, py - ch * 0.42, cw * 0.44, ch * 0.42))
    pipe.addRect(QRectF(px - cw * 0.3, py - ch * 0.5, cw * 0.6, ch * 0.13))
    _shape(painter, pipe, QColor(58, 166, 85, 200))
    painter.setPen(QPen(QColor(30, 92, 48, 210), max(1.2, cw * 0.008)))
    painter.drawLine(QPointF(px - cw * 0.24, py - ch * 0.42), QPointF(px - cw * 0.24, py))
    painter.drawLine(QPointF(px - cw * 0.3, py - ch * 0.5), QPointF(px + cw * 0.3, py - ch * 0.5))

    bx = cx + cw * 1.6
    by = cy - ch * 0.52
    block = QRectF(bx - cw * 0.22, by - cw * 0.22, cw * 0.44, cw * 0.44)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(244, 183, 49, 220)))
    painter.drawRoundedRect(block, cw * 0.02, cw * 0.02)
    painter.setPen(QPen(QColor(150, 96, 20, 220), max(1.2, cw * 0.009)))
    painter.drawRoundedRect(block, cw * 0.02, cw * 0.02)
    font = QFont(style.heading_font)
    font.setPixelSize(int(cw * 0.22))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(120, 70, 10, 230))
    painter.drawText(block, Qt.AlignCenter, "?")

    gx = cx + cw * 1.62
    gy = cy + ch * 0.4
    body = QPainterPath()
    body.addEllipse(QRectF(gx - cw * 0.24, gy - ch * 0.14, cw * 0.48, ch * 0.26))
    _shape(painter, body, QColor(122, 74, 40, 210))
    painter.setPen(QPen(QColor(60, 35, 18, 220), max(1.2, cw * 0.008)))
    painter.drawLine(QPointF(gx - cw * 0.17, gy + ch * 0.11), QPointF(gx - cw * 0.2, gy + ch * 0.18))
    painter.drawLine(QPointF(gx + cw * 0.17, gy + ch * 0.11), QPointF(gx + cw * 0.2, gy + ch * 0.18))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(245, 240, 226, 230)))
    painter.drawEllipse(QPointF(gx - cw * 0.09, gy - ch * 0.02), cw * 0.06, cw * 0.07)
    painter.drawEllipse(QPointF(gx + cw * 0.09, gy - ch * 0.02), cw * 0.06, cw * 0.07)
    painter.setBrush(QBrush(QColor(20, 20, 20, 240)))
    painter.drawEllipse(QPointF(gx - cw * 0.085, gy - ch * 0.02), cw * 0.02, cw * 0.04)
    painter.drawEllipse(QPointF(gx + cw * 0.095, gy - ch * 0.02), cw * 0.02, cw * 0.04)

    sx = max(rect.left() + cw * 0.7, cx - cw * 1.55)
    sy = cy + ch * 0.64
    shell = QPainterPath()
    shell.addEllipse(QRectF(sx - cw * 0.2, sy - ch * 0.13, cw * 0.4, ch * 0.18))
    _shape(painter, shell, QColor(70, 150, 70, 200))
    painter.setPen(QPen(QColor(30, 80, 35, 220), max(1.0, cw * 0.007)))
    for index in range(3):
        painter.drawArc(
            QRectF(sx - cw * 0.12 + index * cw * 0.08, sy - ch * 0.11, cw * 0.12, ch * 0.14),
            0,
            180 * 16,
        )
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(230, 195, 90, 170)))
    painter.drawRect(QRectF(rect.left(), cy + ch * 0.72, rect.width(), ch * 0.018))


def _halo(painter, rect, cx, cy, cw, ch, style) -> None:
    ring = QPainterPath()
    ring.addEllipse(QRectF(cx - cw * 2.1, cy - ch * 0.85, cw * 4.2, ch * 0.9))
    painter.setPen(QPen(QColor(121, 194, 216, 40), max(6.0, cw * 0.055)))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(ring)
    painter.setPen(QPen(QColor(159, 224, 138, 22), max(2.0, cw * 0.02)))
    painter.drawPath(ring)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(20, 40, 48, 70)))
    painter.drawEllipse(QRectF(cx - cw * 2.0, cy - ch * 0.3, cw * 4.0, ch * 0.9))

    hx = cx + cw * 1.7
    hy = cy + ch * 0.05
    helmet = QPainterPath()
    helmet.moveTo(hx - cw * 0.24, hy + ch * 0.2)
    helmet.cubicTo(
        hx - cw * 0.3, hy - ch * 0.1,
        hx - cw * 0.1, hy - ch * 0.28,
        hx + cw * 0.02, hy - ch * 0.28,
    )
    helmet.cubicTo(
        hx + cw * 0.22, hy - ch * 0.26,
        hx + cw * 0.3, hy - ch * 0.05,
        hx + cw * 0.24, hy + ch * 0.2,
    )
    helmet.closeSubpath()
    _shape(painter, helmet, QColor(60, 96, 78, 190))
    visor = QPainterPath()
    visor.moveTo(hx - cw * 0.2, hy - ch * 0.02)
    visor.lineTo(hx + cw * 0.2, hy - ch * 0.02)
    visor.lineTo(hx + cw * 0.14, hy + ch * 0.06)
    visor.lineTo(hx - cw * 0.14, hy + ch * 0.06)
    visor.closeSubpath()
    _shape(painter, visor, QColor(230, 190, 80, 220))
    painter.setPen(QPen(QColor(40, 60, 50, 220), max(1.2, cw * 0.008)))
    painter.drawLine(QPointF(hx, hy - ch * 0.02), QPointF(hx, hy + ch * 0.2))
    painter.drawLine(QPointF(hx - cw * 0.12, hy + ch * 0.2), QPointF(hx + cw * 0.12, hy + ch * 0.2))


def _doom(painter, rect, cx, cy, cw, ch, style) -> None:
    px = max(rect.left() + cw * 0.9, cx - cw * 1.8)
    py = cy - ch * 0.12
    body = QPainterPath()
    body.addEllipse(QRectF(px - cw * 0.48, py - ch * 0.38, cw * 0.96, ch * 0.68))
    _shape(painter, body, QColor(160, 46, 32, 130))
    painter.setPen(QPen(QColor(230, 110, 60, 150), max(1.4, cw * 0.01)))
    for side in (-1, 1):
        path = QPainterPath()
        path.moveTo(px + side * cw * 0.32, py - ch * 0.2)
        path.cubicTo(
            px + side * cw * 0.5, py - ch * 0.55,
            px + side * cw * 0.6, py - ch * 0.5,
            px + side * cw * 0.5, py - ch * 0.25,
        )
        painter.drawPath(path)
    eye = QPainterPath()
    eye.addEllipse(QRectF(px - cw * 0.14, py - ch * 0.16, cw * 0.28, ch * 0.2))
    _shape(painter, eye, QColor(240, 230, 200, 180))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(80, 20, 16, 230)))
    painter.drawEllipse(QPointF(px, py - ch * 0.06), cw * 0.07, cw * 0.09)
    mouth = QPainterPath()
    mouth.moveTo(px - cw * 0.2, py + ch * 0.08)
    mouth.cubicTo(
        px - cw * 0.1, py + ch * 0.2,
        px + cw * 0.1, py + ch * 0.2,
        px + cw * 0.2, py + ch * 0.08,
    )
    painter.setPen(QPen(QColor(90, 20, 16, 200), max(2.0, cw * 0.014)))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(mouth)

    lx = cx + cw * 1.55
    ly = cy - ch * 0.42
    painter.setPen(QPen(QColor(224, 81, 42, 160), max(2.0, cw * 0.014)))
    painter.setBrush(Qt.NoBrush)
    logo = QPainterPath()
    logo.moveTo(lx - cw * 0.3, ly + ch * 0.16)
    logo.lineTo(lx - cw * 0.3, ly - ch * 0.12)
    logo.lineTo(lx - cw * 0.05, ly - ch * 0.12)
    logo.cubicTo(
        lx + cw * 0.2, ly - ch * 0.12,
        lx + cw * 0.2, ly + ch * 0.16,
        lx - cw * 0.05, ly + ch * 0.16,
    )
    logo.closeSubpath()
    painter.drawPath(logo)
    for index in range(3):
        y = ly - ch * 0.05 + index * ch * 0.06
        painter.drawLine(QPointF(lx - cw * 0.22, y), QPointF(lx + cw * 0.12, y))


def _hollow(painter, rect, cx, cy, cw, ch, style) -> None:
    for side in (-1, 1):
        wing = QPainterPath()
        wx = cx + side * cw * 1.6
        wy = cy + ch * 0.02
        wing.moveTo(wx, wy)
        wing.cubicTo(
            wx + side * cw * 0.5, wy - ch * 0.35,
            wx + side * cw * 0.7, wy - ch * 0.05,
            wx + side * cw * 0.35, wy + ch * 0.2,
        )
        wing.cubicTo(
            wx + side * cw * 0.2, wy + ch * 0.05,
            wx + side * cw * 0.1, wy + ch * 0.02,
            wx, wy,
        )
        _shape(painter, wing, QColor(159, 199, 230, 36))
        painter.setPen(QPen(QColor(159, 199, 230, 55), max(1.0, cw * 0.006)))
        painter.setBrush(Qt.NoBrush)
        for index in range(3):
            offset = ch * (0.05 + index * 0.05)
            painter.drawLine(
                QPointF(wx, wy),
                QPointF(wx + side * cw * (0.45 - index * 0.08), wy - offset),
            )

    mx = cx + cw * 1.7
    my = cy - ch * 0.3
    mask = QPainterPath()
    mask.moveTo(mx - cw * 0.18, my + ch * 0.16)
    mask.cubicTo(
        mx - cw * 0.24, my - ch * 0.02,
        mx - cw * 0.14, my - ch * 0.14,
        mx, my - ch * 0.14,
    )
    mask.cubicTo(
        mx + cw * 0.14, my - ch * 0.14,
        mx + cw * 0.24, my - ch * 0.02,
        mx + cw * 0.18, my + ch * 0.16,
    )
    mask.closeSubpath()
    _shape(painter, mask, QColor(222, 232, 242, 190))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(20, 28, 40, 230)))
    painter.drawEllipse(QPointF(mx - cw * 0.07, my), cw * 0.035, cw * 0.06)
    painter.drawEllipse(QPointF(mx + cw * 0.07, my), cw * 0.035, cw * 0.06)
    painter.setBrush(QBrush(QColor(222, 232, 242, 190)))
    for side in (-1, 1):
        horn = QPainterPath()
        horn.moveTo(mx + side * cw * 0.1, my - ch * 0.1)
        horn.cubicTo(
            mx + side * cw * 0.22, my - ch * 0.32,
            mx + side * cw * 0.38, my - ch * 0.4,
            mx + side * cw * 0.42, my - ch * 0.52,
        )
        horn.cubicTo(
            mx + side * cw * 0.3, my - ch * 0.34,
            mx + side * cw * 0.18, my - ch * 0.22,
            mx + side * cw * 0.08, my - ch * 0.08,
        )
        horn.closeSubpath()
        _shape(painter, horn, QColor(210, 222, 235, 170))
