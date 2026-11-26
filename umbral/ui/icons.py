from __future__ import annotations

import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def vector_pixmap(
    name: str,
    color: str | QColor,
    size: int = 16,
    angle: float = 0.0,
) -> QPixmap:
    """Render a crisp HiDPI vector icon pixmap in the given color."""
    dpr = 2
    px = QPixmap(size * dpr, size * dpr)
    px.fill(Qt.transparent)
    px.setDevicePixelRatio(dpr)

    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(size / 16.0, size / 16.0)
    if angle:
        painter.translate(8.0, 8.0)
        painter.rotate(angle)
        painter.translate(-8.0, -8.0)

    qcolor = QColor(color) if not isinstance(color, QColor) else color
    pen = QPen(qcolor, 1.65, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    if name == "plus":
        painter.drawLine(QPointF(8.0, 3.0), QPointF(8.0, 13.0))
        painter.drawLine(QPointF(3.0, 8.0), QPointF(13.0, 8.0))
    elif name == "search":
        painter.drawEllipse(QRectF(2.5, 2.5, 8.5, 8.5))
        painter.drawLine(QPointF(9.7, 9.7), QPointF(13.5, 13.5))
    elif name == "refresh":
        path = QPainterPath()
        path.arcMoveTo(QRectF(2.5, 2.5, 11.0, 11.0), 40)
        path.arcTo(QRectF(2.5, 2.5, 11.0, 11.0), 40, 275)
        painter.drawPath(path)
        # Arrowhead at ~40 deg (top-right)
        painter.drawLine(QPointF(12.3, 4.3), QPointF(13.2, 2.3))
        painter.drawLine(QPointF(12.3, 4.3), QPointF(10.2, 4.7))
    elif name == "play":
        tri = QPainterPath()
        tri.moveTo(4.5, 2.8)
        tri.lineTo(13.0, 8.0)
        tri.lineTo(4.5, 13.2)
        tri.closeSubpath()
        painter.setBrush(qcolor)
        painter.setPen(Qt.NoPen)
        painter.drawPath(tri)
    elif name == "filter":
        painter.drawLine(QPointF(2.5, 4.2), QPointF(13.5, 4.2))
        painter.drawLine(QPointF(4.5, 8.0), QPointF(11.5, 8.0))
        painter.drawLine(QPointF(6.5, 11.8), QPointF(9.5, 11.8))
    elif name == "image":
        painter.drawRoundedRect(QRectF(2.2, 3.0, 11.6, 10.0), 1.8, 1.8)
        painter.drawEllipse(QPointF(5.5, 6.2), 1.0, 1.0)
        hills = QPainterPath()
        hills.moveTo(3.2, 11.8)
        hills.lineTo(6.5, 8.5)
        hills.lineTo(8.8, 10.7)
        hills.lineTo(10.8, 8.8)
        hills.lineTo(12.8, 11.8)
        painter.drawPath(hills)
    elif name == "chevron_left":
        path = QPainterPath()
        path.moveTo(10.2, 3.2)
        path.lineTo(5.5, 8.0)
        path.lineTo(10.2, 12.8)
        painter.drawPath(path)
    elif name == "chevron_right":
        path = QPainterPath()
        path.moveTo(5.8, 3.2)
        path.lineTo(10.5, 8.0)
        path.lineTo(5.8, 12.8)
        painter.drawPath(path)
    elif name == "close":
        painter.drawLine(QPointF(4.0, 4.0), QPointF(12.0, 12.0))
        painter.drawLine(QPointF(12.0, 4.0), QPointF(4.0, 12.0))
    elif name == "spinner":
        for i in range(8):
            alpha = int(60 + (i / 7.0) * 195)
            seg_color = QColor(qcolor)
            seg_color.setAlpha(alpha)
            painter.setPen(QPen(seg_color, 1.6, Qt.SolidLine, Qt.RoundCap))
            rad = math.radians(i * 45)
            x1 = 8.0 + math.cos(rad) * 3.6
            y1 = 8.0 + math.sin(rad) * 3.6
            x2 = 8.0 + math.cos(rad) * 5.8
            y2 = 8.0 + math.sin(rad) * 5.8
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    painter.end()
    return px


def vector_icon(
    name: str,
    color: str | QColor,
    size: int = 16,
    angle: float = 0.0,
) -> QIcon:
    """Return a QIcon wrapping vector_pixmap."""
    return QIcon(vector_pixmap(name, color, size=size, angle=angle))
