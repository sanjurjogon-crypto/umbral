from __future__ import annotations

import math
import random
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
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
)

from .style import active as active_style
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..models import Game


def _shade(color: QColor, factor: float) -> QColor:
    if factor >= 0:
        return color.lighter(int(100 + factor * 100))
    return color.darker(int(100 + (-factor) * 100))


class Backdrop(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("root")
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._rng = random.Random(41)
        self._particles = self._make_particles()
        self._pixmap: Optional[QPixmap] = None
        self._time = 0.0
        self._style_key = active_style().key
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _make_particles(self) -> list[list[float]]:
        style = active_style()
        count = {
            "sheikah": 34,
            "leaves": 30,
            "golddust": 70,
            "dust": 38,
            "spores": 40,
            "bricks": 26,
            "scanlines": 22,
            "lava": 30,
            "motes": 38,
            "embers": 44,
        }.get(style.motif, 38)
        rng = self._rng
        return [
            [
                rng.uniform(0.02, 0.98),
                rng.uniform(0.05, 1.0),
                rng.uniform(1.2, 2.8),
                rng.uniform(24, 72),
                rng.uniform(0.006, 0.02),
                rng.uniform(-0.006, 0.006),
            ]
            for _ in range(count)
        ]

    def apply_style(self, style_key: str) -> None:
        self._style_key = style_key
        self._rng = random.Random(41)
        self._particles = self._make_particles()
        self._pixmap = None
        self.update()

    def _tick(self) -> None:
        self._time += 0.05
        motif = active_style().motif
        falling = motif in {"leaves", "spores", "golddust"}
        for particle in self._particles:
            particle[0] += particle[5] * 0.05
            particle[1] -= (-particle[4] if falling else particle[4]) * 0.05
            if particle[1] < -0.02:
                particle[1] = 1.02
                particle[0] = self._rng.uniform(0.02, 0.98)
            if particle[0] < -0.02:
                particle[0] = 1.02
            elif particle[0] > 1.02:
                particle[0] = -0.02
        self.update()

    def _render_static(self) -> None:
        style = active_style()
        pixmap = QPixmap(self.size())
        pixmap.fill(QColor(style.bg))
        painter = QPainter(pixmap)
        width = max(1, self.width())
        height = max(1, self.height())

        base = QLinearGradient(0, 0, 0, height)
        base.setColorAt(0.0, QColor(style.backdrop_top))
        base.setColorAt(0.55, QColor(style.bg))
        base.setColorAt(1.0, QColor(style.backdrop_bottom))
        painter.fillRect(pixmap.rect(), QBrush(base))

        glow_color = QColor(style.accent)
        glow = QRadialGradient(width * 0.5, height * 0.18, width * 0.75)
        glow.setColorAt(0.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 22))
        glow.setColorAt(0.55, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 7))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(pixmap.rect(), QBrush(glow))

        self._paint_motif(painter, style, width, height)

        vignette = QRadialGradient(width * 0.5, height * 0.48, max(width, height) * 0.72)
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.62, QColor(0, 0, 0, 34))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 200))
        painter.fillRect(pixmap.rect(), QBrush(vignette))
        painter.end()
        self._pixmap = pixmap

    def _paint_motif(self, painter: QPainter, style, width: int, height: int) -> None:
        color = QColor(style.motif_color)
        painter.setPen(Qt.NoPen)
        if style.motif == "scanlines":
            line = QColor(color)
            line.setAlpha(10)
            painter.setPen(QPen(line, 1))
            step = 6
            for y in range(0, height, step):
                painter.drawLine(0, y, width, y)
            painter.setPen(Qt.NoPen)
            band = QColor(color)
            band.setAlpha(16)
            painter.fillRect(QRectF(0, height * 0.12, width, 2), band)
        elif style.motif == "bricks":
            line = QColor(color)
            line.setAlpha(14)
            painter.setPen(QPen(line, 1))
            brick_w = 90
            brick_h = 44
            for row, y in enumerate(range(0, height, brick_h)):
                painter.drawLine(0, y, width, y)
                offset = 0 if row % 2 == 0 else brick_w // 2
                for x in range(-brick_w, width + brick_w, brick_w):
                    painter.drawLine(x + offset, y, x + offset, y + brick_h)
            painter.setPen(Qt.NoPen)
        elif style.motif == "paper":
            line = QColor(color)
            line.setAlpha(22)
            painter.setPen(QPen(line, 1))
            step = 34
            for y in range(0, height, step):
                painter.drawLine(0, y, width, y)
            painter.setPen(Qt.NoPen)
            dot = QColor(color)
            dot.setAlpha(28)
            painter.setBrush(QBrush(dot))
            for y in range(step, height, step):
                for x in range(step, width, step):
                    painter.drawEllipse(QPointF(x, y), 1.2, 1.2)
        elif style.motif in {"sheikah", "leaves"}:
            line = QColor(color)
            line.setAlpha(18)
            painter.setPen(QPen(line, 1))
            center = QPointF(width * 0.5, height * 0.3)
            for radius in (120, 190, 260):
                painter.drawEllipse(center, radius, radius)
            painter.setPen(Qt.NoPen)
        elif style.motif == "dust":
            cone = QPainterPath()
            cone.moveTo(width * 0.14, -height * 0.05)
            cone.lineTo(width * 0.42, -height * 0.05)
            cone.lineTo(width * 0.72, height * 1.05)
            cone.lineTo(width * 0.18, height * 1.05)
            cone.closeSubpath()
            light = QLinearGradient(width * 0.14, 0, width * 0.6, height)
            beam = QColor(color)
            beam.setAlpha(26)
            clear = QColor(color)
            clear.setAlpha(0)
            light.setColorAt(0.0, beam)
            light.setColorAt(1.0, clear)
            painter.fillPath(cone, QBrush(light))

    def paintEvent(self, event) -> None:
        if self._pixmap is None or self._pixmap.size() != self.size():
            self._render_static()
        painter = QPainter(self)
        if self._pixmap is not None:
            painter.drawPixmap(0, 0, self._pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        style = active_style()
        color = QColor(style.ember_color)
        width = max(1, self.width())
        height = max(1, self.height())
        square = style.motif in {"bricks", "lava"}
        for x, y, radius, alpha, _speed, _drift in self._particles:
            flicker = 0.55 + 0.45 * math.sin(self._time * 1.9 + x * 37.0)
            color.setAlpha(max(0, min(255, int(alpha * flicker))))
            painter.setBrush(QBrush(color))
            if square:
                size = radius * 1.3
                painter.drawRect(QRectF(x * width - size / 2, y * height - size / 2, size, size))
            else:
                painter.drawEllipse(QPointF(x * width, y * height), radius, radius)
        painter.end()


class FlowLayout(QLayout):
    def __init__(self, parent: Optional[QWidget] = None, margin: int = 0, h_spacing: int = 18, v_spacing: int = 22) -> None:
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_spacing
            if next_x - self._h_spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + self._v_spacing
                next_x = x + hint.width() + self._h_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


class CoverArt(QWidget):
    def __init__(self, game: Game, width: int = 202, height: int = 288, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game = game
        self._pixmap: Optional[QPixmap] = None
        self._loaded_path = ""
        self.setFixedSize(width, height)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._load_cover()

    def _load_cover(self) -> None:
        from ..covers import game_cover

        path = game_cover(self.game)
        if path is None:
            self._pixmap = None
            self._loaded_path = ""
            return
        key = str(path)
        if key == self._loaded_path and self._pixmap is not None:
            return
        pixmap = QPixmap(key)
        self._pixmap = None if pixmap.isNull() else pixmap
        self._loaded_path = key

    def set_game(self, game: Game) -> None:
        self.game = game
        self._loaded_path = ""
        self._load_cover()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect().adjusted(1, 1, -1, -1)
        style = active_style()
        radius = style.radius
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), radius, radius)
        painter.setClipPath(path)

        accent = QColor(style.accent)

        if self._pixmap is not None and not self._pixmap.isNull():
            self._paint_cover_image(painter, rect, accent)
        else:
            self._paint_generated(painter, rect, accent)

        painter.setClipping(False)
        border = QColor(style.accent)
        border.setAlpha(80)
        painter.setPen(QPen(border, style.border_width))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

    def _paint_cover_image(self, painter: QPainter, rect: QRect, accent: QColor) -> None:
        pixmap = self._pixmap
        if pixmap is None:
            return
        ratio = pixmap.width() / max(1, pixmap.height())
        target_ratio = rect.width() / max(1, rect.height())
        style = active_style()
        if ratio > target_ratio * 1.25:
            painter.fillRect(rect, QColor(style.canvas))
            small = QSize(
                max(1, int(rect.width() * 0.1)),
                max(1, int(rect.height() * 0.1)),
            )
            backdrop = pixmap.scaled(
                small, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            ).scaled(rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.setOpacity(0.4)
            painter.drawPixmap(
                QPoint(
                    rect.center().x() - backdrop.width() // 2,
                    rect.center().y() - backdrop.height() // 2,
                ),
                backdrop,
            )
            painter.setOpacity(1.0)
            scaled = pixmap.scaled(
                rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            painter.drawPixmap(
                QPoint(
                    rect.center().x() - scaled.width() // 2,
                    rect.center().y() - scaled.height() // 2,
                ),
                scaled,
            )
        else:
            scaled = pixmap.scaled(
                rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            source_x = max(0, (scaled.width() - rect.width()) // 2)
            source_y = max(0, (scaled.height() - rect.height()) // 3)
            painter.drawPixmap(
                rect.topLeft(),
                scaled.copy(QRect(source_x, source_y, rect.width(), rect.height())),
            )

        shade = QLinearGradient(0, self.height() * 0.62, 0, self.height())
        shade.setColorAt(0.0, QColor(0, 0, 0, 0))
        shade.setColorAt(1.0, QColor(0, 0, 0, 190))
        painter.fillRect(rect, QBrush(shade))

        self._paint_pill(painter, accent, top=False)

    def _paint_generated(self, painter: QPainter, rect: QRect, accent: QColor) -> None:
        style = active_style()
        base = QLinearGradient(0, 0, self.width(), self.height())
        base.setColorAt(0.0, QColor(style.surface_2))
        base.setColorAt(0.55, _shade(accent, -0.86))
        base.setColorAt(1.0, _shade(accent, -0.72))
        painter.fillRect(rect, QBrush(base))

        glow = QRadialGradient(self.width() * 0.7, self.height() * 0.26, self.width() * 0.95)
        glow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 55))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, QBrush(glow))

        outline = QColor(style.accent)
        outline.setAlpha(20)
        painter.setPen(QPen(outline, 1))
        inset = rect.adjusted(8, 8, -8, -8)
        painter.drawRect(inset)

        initials = "".join(word[0] for word in self.game.title.split()[:2]).upper() or "?"
        monogram = QFont(style.heading_font)
        monogram.setPixelSize(86)
        monogram.setWeight(QFont.Medium)
        monogram.setLetterSpacing(QFont.AbsoluteSpacing, 4)
        painter.setFont(monogram)
        text_color = QColor(style.text)
        text_color.setAlpha(50)
        painter.setPen(text_color)
        painter.drawText(rect.adjusted(0, 12, 0, 0), Qt.AlignCenter, initials)

        shade = QLinearGradient(0, self.height() * 0.42, 0, self.height())
        shade.setColorAt(0.0, QColor(0, 0, 0, 0))
        shade.setColorAt(1.0, QColor(0, 0, 0, 228))
        painter.fillRect(rect, QBrush(shade))

        self._paint_pill(painter, accent)
        self._paint_title(painter, accent)

    def _paint_pill(self, painter: QPainter, accent: QColor, top: bool = True) -> None:
        style = active_style()
        pill_text = (self.game.system or "JUEGO").upper()
        pill_font = QFont(style.heading_font)
        pill_font.setPixelSize(9)
        pill_font.setWeight(QFont.Medium)
        pill_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        painter.setFont(pill_font)
        metrics = QFontMetrics(pill_font)
        pill_width = metrics.horizontalAdvance(pill_text) + 16
        y = 14 if top else self.height() - 50
        pill = QRect(14, y, pill_width, 21)
        border = QColor(style.accent)
        border.setAlpha(110)
        background = QColor(style.bg)
        background.setAlpha(210)
        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        painter.drawRect(pill)
        painter.setPen(QColor(style.accent_2))
        painter.drawText(pill, Qt.AlignCenter, pill_text)

    def _paint_title(self, painter: QPainter, accent: QColor) -> None:
        style = active_style()
        title_font = QFont(style.heading_font)
        title_font.setPixelSize(18)
        title_font.setWeight(QFont.Medium)
        title_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
        painter.setFont(title_font)
        painter.setPen(QColor(style.accent_2))
        title_rect = QRect(16, self.height() - 94, self.width() - 32, 72)
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignBottom | Qt.TextWordWrap, self.game.title)

        line = QColor(style.accent)
        line.setAlpha(200)
        painter.setPen(QPen(line, 1))
        painter.drawLine(16, self.height() - 100, 58, self.height() - 100)


class GameCard(QFrame):
    play_requested = Signal(object)
    details_requested = Signal(object)
    context_requested = Signal(object, object)

    def __init__(self, game: Game, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game = game
        self.setObjectName("card")
        self.setFixedWidth(222)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setProperty("hovered", False)

        body = QVBoxLayout(self)
        body.setContentsMargins(10, 10, 10, 12)
        body.setSpacing(8)

        self.cover = CoverArt(game)
        body.addWidget(self.cover, 0, Qt.AlignHCenter)

        self.title_label = QLabel(game.title)
        self.title_label.setObjectName("cardTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumHeight(38)
        body.addWidget(self.title_label)

        self.subtitle_label = QLabel(game.subtitle or game.system)
        self.subtitle_label.setObjectName("muted")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("font-size: 12px;")
        body.addWidget(self.subtitle_label)

        self.play_button = QPushButton("▶", self.cover)
        self.play_button.setObjectName("play")
        self.play_button.setCursor(Qt.PointingHandCursor)
        self.play_button.setFixedSize(36, 36)
        self.play_button.move(202 - 36 - 12, 288 - 36 - 52)
        self.play_button.clicked.connect(lambda: self.play_requested.emit(self.game))
        self.play_button.raise_()

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(18)
        self._shadow.setOffset(0, 7)
        self._shadow.setColor(QColor(0, 0, 0, 130))
        self.setGraphicsEffect(self._shadow)

        self._animation = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

        self._details_timer = QTimer(self)
        self._details_timer.setSingleShot(True)
        self._details_timer.setInterval(180)
        self._details_timer.timeout.connect(lambda: self.details_requested.emit(self.game))

    def _set_hovered(self, hovered: bool) -> None:
        self.setProperty("hovered", hovered)
        self.style().unpolish(self)
        self.style().polish(self)
        self._animation.stop()
        self._animation.setStartValue(self._shadow.blurRadius())
        self._animation.setEndValue(36 if hovered else 18)
        self._animation.start()
        self._shadow.setColor(QColor(0, 0, 0, 160) if hovered else QColor(0, 0, 0, 130))

    def enterEvent(self, event) -> None:
        self._set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_hovered(False)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._details_timer.start()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self._details_timer.stop()
        self.play_requested.emit(self.game)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._details_timer.stop()
        self.context_requested.emit(self.game, event.globalPos())
        event.accept()


class SectionHeader(QWidget):
    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        bar = QFrame()
        bar.setObjectName("accentBar")
        bar.setFixedSize(2, 18)
        row.addWidget(bar)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        row.addWidget(label)
        row.addStretch(1)


class CardRow(QWidget):
    play_requested = Signal(object)
    details_requested = Signal(object)
    context_requested = Signal(object, object)

    def __init__(self, title: str, games: list[Game], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QScrollArea

        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        body.addWidget(SectionHeader(title))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFixedHeight(400)

        inner = QWidget()
        row = QHBoxLayout(inner)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)
        for game in games:
            card = GameCard(game)
            card.play_requested.connect(self.play_requested)
            card.details_requested.connect(self.details_requested)
            card.context_requested.connect(self.context_requested)
            row.addWidget(card)
        row.addStretch(1)
        scroll.setWidget(inner)
        body.addWidget(scroll)


class HeroBanner(QFrame):
    play_requested = Signal(object)
    details_requested = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("hero")
        self.setFixedHeight(320)
        self.game: Optional[Game] = None
        self.setAttribute(Qt.WA_StyledBackground, False)

        body = QHBoxLayout(self)
        body.setContentsMargins(34, 30, 34, 30)
        body.setSpacing(26)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.kicker = QLabel("DESTACADO")
        self.kicker.setObjectName("kicker")
        left.addWidget(self.kicker)
        self.title = QLabel("")
        self.title.setObjectName("heroTitle")
        self.title.setWordWrap(True)
        left.addWidget(self.title)
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("muted")
        left.addWidget(self.subtitle)
        self.meta = QLabel("")
        self.meta.setObjectName("muted")
        left.addWidget(self.meta)
        self.description = QLabel("")
        self.description.setObjectName("muted")
        self.description.setWordWrap(True)
        self.description.setMaximumHeight(54)
        left.addWidget(self.description)
        left.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.play_button = QPushButton("Jugar ahora")
        self.play_button.setObjectName("primary")
        self.play_button.setCursor(Qt.PointingHandCursor)
        self.play_button.clicked.connect(lambda: self.game and self.play_requested.emit(self.game))
        self.details_button = QPushButton("Ver detalles")
        self.details_button.setObjectName("ghost")
        self.details_button.setCursor(Qt.PointingHandCursor)
        self.details_button.clicked.connect(lambda: self.game and self.details_requested.emit(self.game))
        buttons.addWidget(self.play_button)
        buttons.addWidget(self.details_button)
        buttons.addStretch(1)
        left.addLayout(buttons)

        body.addLayout(left, 1)

        self.cover = CoverArt(
            Game(
                id="placeholder",
                title="Umbral",
                system="Biblioteca",
                system_key="placeholder",
            ),
            212,
            302,
        )
        self.cover.setVisible(False)
        body.addWidget(self.cover, 0, Qt.AlignVCenter)

    def set_game(self, game: Optional[Game]) -> None:
        self.game = game
        if game is None:
            self.kicker.setText("BIENVENIDO")
            self.title.setText("Tu biblioteca empieza aquí")
            self.subtitle.setText("Detecta tus emuladores y ports, o añade un juego a mano.")
            self.meta.setText("")
            self.description.setText("")
            self.play_button.setVisible(False)
            self.details_button.setVisible(False)
            self.cover.setVisible(False)
            self.update()
            return

        self.kicker.setText("CONTINUAR JUGANDO" if game.last_played else "DESTACADO")
        self.title.setText(game.title)
        self.subtitle.setText(game.subtitle or game.system)
        bits: list[str] = []
        if not (game.subtitle and game.subtitle.startswith(game.system)):
            bits.append(game.system)
        if game.year:
            bits.append(str(game.year))
        if game.genre:
            bits.append(game.genre)
        bits.append(game.playtime_text)
        self.meta.setText("   ·   ".join(bits))
        self.description.setText(game.description or "")
        self.play_button.setVisible(True)
        self.details_button.setVisible(True)
        self.cover.set_game(game)
        self.cover.setVisible(True)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        style = active_style()
        radius = style.radius
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), radius, radius)
        painter.setClipPath(path)

        base = QLinearGradient(0, 0, self.width(), self.height())
        base.setColorAt(0.0, QColor(style.surface_2))
        base.setColorAt(0.65, QColor(style.surface))
        base.setColorAt(1.0, QColor(style.bg))
        painter.fillRect(rect, QBrush(base))

        accent = QColor(style.accent)
        glow = QRadialGradient(self.width() * 0.82, self.height() * 0.45, self.width() * 0.55)
        glow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 46))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, QBrush(glow))

        lines = QColor(style.accent)
        lines.setAlpha(12)
        painter.setPen(QPen(lines, 1))
        for offset in range(-self.height(), self.width(), 42):
            painter.drawLine(offset, 0, offset + self.height(), self.height())

        painter.setClipping(False)
        border = QColor(style.accent)
        border.setAlpha(60)
        painter.setPen(QPen(border, style.border_width))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)


class StatTile(QFrame):
    def __init__(self, value: str, label: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("tile")
        self.setMinimumHeight(112)
        body = QVBoxLayout(self)
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(4)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("statValue")
        self.label = QLabel(label)
        self.label.setObjectName("statLabel")
        body.addWidget(self.value_label)
        body.addWidget(self.label)
        body.addStretch(1)

    def set_values(self, value: str, label: str) -> None:
        self.value_label.setText(value)
        self.label.setText(label)


class HealthRow(QFrame):
    action_clicked = Signal()

    def __init__(
        self,
        level: str,
        title: str,
        detail: str,
        action_text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("health")
        style = active_style()
        colors = {
            "error": style.danger,
            "warn": style.accent,
            "info": style.info,
            "ok": style.success,
        }
        color = colors.get(level, style.muted)
        body = QHBoxLayout(self)
        body.setContentsMargins(16, 13, 16, 13)
        body.setSpacing(12)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color}; font-size: 12px;")
        body.addWidget(dot)
        text = QVBoxLayout()
        text.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: 700;")
        detail_label = QLabel(detail)
        detail_label.setObjectName("muted")
        detail_label.setWordWrap(True)
        text.addWidget(title_label)
        text.addWidget(detail_label)
        body.addLayout(text, 1)
        if action_text:
            button = QPushButton(action_text)
            button.setObjectName("ghost")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(self.action_clicked)
            body.addWidget(button)


class EmptyState(QWidget):
    action = Signal()

    def __init__(self, title: str, description: str, button_text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        body = QVBoxLayout(self)
        body.setContentsMargins(28, 34, 28, 34)
        body.setSpacing(10)
        body.setAlignment(Qt.AlignCenter)
        glyph = QLabel("◇")
        glyph.setStyleSheet(f"font-size: 42px; color: {active_style().accent};")
        glyph.setAlignment(Qt.AlignCenter)
        body.addWidget(glyph)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("h2")
        self.title_label.setAlignment(Qt.AlignCenter)
        body.addWidget(self.title_label)
        self.description_label = QLabel(description)
        self.description_label.setObjectName("muted")
        self.description_label.setAlignment(Qt.AlignCenter)
        self.description_label.setWordWrap(True)
        self.description_label.setMaximumWidth(460)
        body.addWidget(self.description_label, 0, Qt.AlignHCenter)
        self.button: Optional[QPushButton] = None
        if button_text:
            self.button = QPushButton(button_text)
            self.button.setObjectName("primary")
            self.button.setCursor(Qt.PointingHandCursor)
            self.button.clicked.connect(self.action)
            body.addWidget(self.button, 0, Qt.AlignHCenter)

    def set_text(self, title: str, description: str, button_text: str = "") -> None:
        self.title_label.setText(title)
        self.description_label.setText(description)
        if self.button is not None:
            self.button.setVisible(bool(button_text))
            if button_text:
                self.button.setText(button_text)


class UpdateBanner(QFrame):
    install_clicked = Signal()
    postpone_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateBannerShell")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(568)
        self._version = ""
        self._target = QPoint(0, 0)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(48)
        self._shadow.setOffset(0, 14)
        self._shadow.setColor(QColor(0, 0, 0, 210))
        self.setGraphicsEffect(self._shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        self._panel = QFrame()
        self._panel.setObjectName("updateBanner")
        outer.addWidget(self._panel)

        self._effect = QGraphicsOpacityEffect(self._panel)
        self._effect.setOpacity(0.0)
        self._panel.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._slide = QPropertyAnimation(self, b"pos", self)

        body = QVBoxLayout(self._panel)
        body.setContentsMargins(22, 20, 22, 20)
        body.setSpacing(8)

        self.title = QLabel("¡Estás de suerte! Ya que:")
        self.title.setObjectName("bannerTitle")
        self.title.setWordWrap(True)
        body.addWidget(self.title)

        self.line1 = QLabel("- Gonzalo es el puto amo")
        self.line1.setObjectName("bannerText")
        self.line1.setWordWrap(True)
        body.addWidget(self.line1)

        self.line2 = QLabel("- Hay una nueva actualización de Umbral disponible")
        self.line2.setObjectName("bannerText")
        self.line2.setWordWrap(True)
        body.addWidget(self.line2)

        self.detail = QLabel("")
        self.detail.setObjectName("bannerDetail")
        self.detail.setWordWrap(True)
        self.detail.hide()
        body.addWidget(self.detail)

        body.addSpacing(6)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.action = QPushButton("Actualizar ahora")
        self.action.setObjectName("bannerPrimary")
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.clicked.connect(self.install_clicked)
        self.later = QPushButton("Ahora no")
        self.later.setObjectName("bannerGhost")
        self.later.setCursor(Qt.PointingHandCursor)
        self.later.clicked.connect(self.postpone_clicked)
        actions.addWidget(self.action)
        actions.addWidget(self.later)
        actions.addStretch(1)
        body.addLayout(actions)
        self.hide()

    def current_version(self) -> str:
        return self._version

    def show_update(self, version: str) -> None:
        self._version = version
        self.title.setText("¡Estás de suerte! Ya que:")
        self.line1.setText("- Gonzalo es el puto amo")
        self.line2.setText("- Hay una nueva actualización de Umbral disponible")
        self.line1.show()
        self.line2.show()
        if version:
            self.detail.setText(f"Versión {version} · se reinicia sola al terminar")
        else:
            self.detail.setText("Preparando la actualización")
        self.detail.show()
        self.action.setText("Actualizar ahora")
        self.action.setEnabled(True)
        self.later.setEnabled(True)
        self.later.show()
        self.adjustSize()
        self._target = self._target_position()
        self.move(self._target.x(), self._target.y() + 18)
        self.show()
        self.raise_()
        self._animate_in()

    def show_progress(self, done: int, total: int) -> None:
        percent = int(done * 100 / total) if total > 0 else 0
        self.title.setText(f"Descargando Umbral {self._version}…")
        self.line1.hide()
        self.line2.hide()
        self.detail.setText(f"{percent} %")
        self.action.setText("Descargando…")
        self.action.setEnabled(False)
        self.later.setEnabled(False)
        self._refit()

    def show_error(self, message: str) -> None:
        self.title.setText("No se pudo actualizar")
        self.line1.hide()
        self.line2.hide()
        self.detail.setText(message)
        self.action.setText("Reintentar")
        self.action.setEnabled(True)
        self.later.setEnabled(True)
        self._refit()

    def _refit(self) -> None:
        self.adjustSize()
        if self.isVisible():
            self.reposition()

    def hideEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if self._fade is not None:
            self._fade.stop()
        if self._slide is not None:
            self._slide.stop()
        self._effect.setOpacity(0.0)
        super().hideEvent(event)

    def reposition(self) -> None:
        if not self.isVisible():
            return
        self._target = self._target_position()
        self.move(self._target)

    def _target_position(self) -> QPoint:
        parent = self.parentWidget()
        if parent is None:
            return QPoint(0, 0)
        x = max(18, (parent.width() - self.width()) // 2)
        y = max(18, (parent.height() - self.height()) // 2 - 20)
        return QPoint(x, y)

    def _animate_in(self) -> None:
        if self._fade is None or self._slide is None:
            return
        self._fade.stop()
        self._slide.stop()
        self._effect.setOpacity(0.0)
        self._fade.setDuration(240)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.start()
        self._slide.setDuration(260)
        self._slide.setStartValue(QPoint(self._target.x(), self._target.y() + 18))
        self._slide.setEndValue(self._target)
        self._slide.setEasingCurve(QEasingCurve.OutCubic)
        self._slide.start()


class Toast(QLabel):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignCenter)
        self.hide()
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._animation = QPropertyAnimation(self._effect, b"opacity", self)
        self._animation.setDuration(220)
        self._animation.finished.connect(self._on_animation_finished)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def show_message(self, text: str, milliseconds: int = 3400) -> None:
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self._effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(milliseconds)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent:
            self.move(parent.width() - self.width() - 28, parent.height() - self.height() - 28)

    def _fade_out(self) -> None:
        self._animation.stop()
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.start()

    def _on_animation_finished(self) -> None:
        if self._effect.opacity() <= 0.01:
            self.hide()


class StylePreview(QFrame):
    clicked = Signal(str)

    def __init__(self, style, selected: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.style = style
        self.selected = selected
        self._hovered = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(196, 104)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip(f"{style.game}: {style.blurb}")

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.style.key)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        style = self.style
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), max(4, style.radius), max(4, style.radius))
        painter.setClipPath(path)

        base = QLinearGradient(0, 0, rect.width(), rect.height())
        base.setColorAt(0.0, QColor(style.surface_2))
        base.setColorAt(0.65, QColor(style.bg))
        base.setColorAt(1.0, QColor(style.backdrop_bottom))
        painter.fillRect(rect, QBrush(base))

        accent = QColor(style.accent)
        glow = QRadialGradient(rect.width() * 0.85, rect.height() * 0.3, rect.width() * 0.7)
        glow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 70 if self._hovered else 46))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, QBrush(glow))

        band = QLinearGradient(0, 0, rect.width(), 0)
        band.setColorAt(0.0, QColor(style.accent))
        band.setColorAt(1.0, QColor(style.accent_2))
        painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), 3), QBrush(band))

        title_font = QFont(style.heading_font)
        title_font.setPixelSize(15)
        title_font.setWeight(QFont.DemiBold)
        title_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        painter.setFont(title_font)
        painter.setPen(QColor(style.accent_2))
        painter.drawText(QRect(14, 18, rect.width() - 28, 22), Qt.AlignLeft | Qt.AlignVCenter, style.name)

        body_font = QFont(style.body_font)
        body_font.setPixelSize(11)
        painter.setFont(body_font)
        painter.setPen(QColor(style.muted))
        painter.drawText(
            QRect(14, 40, rect.width() - 28, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            style.game,
        )
        painter.setPen(QColor(style.muted_2))
        painter.drawText(
            QRect(14, 58, rect.width() - 28, 30),
            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
            style.blurb,
        )

        swatches = [style.accent, style.accent_2, style.success, style.danger]
        for index, color in enumerate(swatches):
            chip = QRect(14 + index * 16, 90, 10, 6)
            painter.fillRect(chip, QColor(color))

        painter.setClipping(False)
        outline = QColor(style.accent if (self.selected or self._hovered) else style.border)
        outline.setAlpha(255 if self.selected else (170 if self._hovered else 120))
        painter.setPen(QPen(outline, 2 if self.selected else 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, max(4, style.radius), max(4, style.radius))
        if self.selected:
            dot = QColor(style.accent_2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(dot))
            painter.drawEllipse(QPointF(rect.right() - 14, rect.top() + 14), 4, 4)
        painter.end()

