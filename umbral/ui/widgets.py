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

from .icons import vector_icon
from .style import active as active_style, is_reduced_motion
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..models import Game
from ..paths import assets_dir


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
        self._timer.setInterval(40)
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

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

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
    def __init__(
        self,
        game: Game,
        width: int = 202,
        height: int = 288,
        parent: Optional[QWidget] = None,
        *,
        show_pill: bool = True,
        radius: Optional[float] = None,
    ) -> None:
        super().__init__(parent)
        self.game = game
        self._show_pill = show_pill
        self._custom_radius = radius
        self._pixmap: Optional[QPixmap] = None
        self._cached_render: Optional[QPixmap] = None
        self._cached_style_key = ""
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
            self._cached_render = None
            return
        key = str(path)
        if key == self._loaded_path and self._pixmap is not None:
            return
        pixmap = QPixmap(key)
        self._pixmap = None if pixmap.isNull() else pixmap
        self._loaded_path = key
        self._cached_render = None

    def set_game(self, game: Game) -> None:
        self.game = game
        self._loaded_path = ""
        self._cached_render = None
        self._load_cover()
        self.update()

    def paintEvent(self, event) -> None:
        from .cases import case_profile, paint_console_case

        style = active_style()
        dpr = min(2.0, max(1.0, float(self.devicePixelRatioF())))
        target_sz = QSize(
            max(1, int(round(self.width() * dpr))),
            max(1, int(round(self.height() * dpr))),
        )
        if (
            self._cached_render is None
            or self._cached_render.size() != target_sz
            or self._cached_style_key != style.key
        ):
            rendered = QPixmap(target_sz)
            rendered.setDevicePixelRatio(dpr)
            rendered.fill(Qt.transparent)
            buf = QPainter(rendered)
            buf.setRenderHint(QPainter.Antialiasing)
            buf.setRenderHint(QPainter.SmoothPixmapTransform)
            rect = self.rect().adjusted(1, 1, -1, -1)
            profile = case_profile(self.game)
            accent = QColor(style.accent)
            # Match the exact front case rendering used in the Library shelf
            case_aspect = max(0.45, float(profile.w_scale) / max(0.45, float(profile.h_scale)))
            base_aspect = 0.72
            target_aspect = base_aspect * case_aspect
            avail_w = float(rect.width())
            avail_h = float(rect.height())
            if avail_w / max(1.0, avail_h) > target_aspect:
                case_h = avail_h
                case_w = case_h * target_aspect
            else:
                case_w = avail_w
                case_h = case_w / target_aspect
            case_frame = QRectF(
                rect.center().x() - case_w / 2.0,
                rect.center().y() - case_h / 2.0,
                case_w,
                case_h,
            )
            radius = self._custom_radius if self._custom_radius is not None else profile.radius
            path = QPainterPath()
            path.addRoundedRect(case_frame, radius, radius)
            buf.setClipPath(path)

            if profile.shell_kind == "pc_keepcase":
                if self._pixmap is not None and not self._pixmap.isNull():
                    self._paint_cover_image(buf, case_frame.toRect(), accent)
                else:
                    self._paint_generated(buf, case_frame.toRect(), accent)
            else:
                paint_console_case(
                    buf,
                    case_frame,
                    profile,
                    self._pixmap,
                    lambda p, r: self._paint_generated(p, r.toRect(), accent),
                )

            buf.setClipping(False)
            border = QColor(style.accent)
            border.setAlpha(75)
            buf.setPen(QPen(border, style.border_width))
            buf.setBrush(Qt.NoBrush)
            buf.drawRoundedRect(case_frame, radius, radius)
            buf.end()
            self._cached_render = rendered
            self._cached_style_key = style.key

        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cached_render)

    def _paint_cover_image(self, painter: QPainter, rect: QRect, accent: QColor) -> None:
        pixmap = self._pixmap
        if pixmap is None:
            return
        ratio = pixmap.width() / max(1, pixmap.height())
        target_ratio = rect.width() / max(1, rect.height())
        if ratio > target_ratio * 1.25:
            dpr = min(2.0, max(1.0, float(self.devicePixelRatioF())))
            hi_sz = QSize(
                max(1, int(round(rect.width() * dpr))),
                max(1, int(round(rect.height() * dpr))),
            )
            painter.fillRect(rect, QColor("#080705"))
            small = QSize(max(1, int(hi_sz.width() * 0.14)), max(1, int(hi_sz.height() * 0.14)))
            backdrop = pixmap.scaled(
                small, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            ).scaled(hi_sz, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            backdrop.setDevicePixelRatio(dpr)
            painter.setOpacity(0.42)
            painter.drawPixmap(rect.topLeft(), backdrop)
            painter.setOpacity(1.0)
            scaled = pixmap.scaled(
                hi_sz, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            scaled.setDevicePixelRatio(dpr)
            draw_w = scaled.width() / dpr
            draw_h = scaled.height() / dpr
            painter.drawPixmap(
                QPointF(
                    rect.center().x() - draw_w / 2.0,
                    rect.center().y() - draw_h / 2.0,
                ),
                scaled,
            )
        else:
            dpr = min(2.0, max(1.0, float(self.devicePixelRatioF())))
            hi_sz = QSize(
                max(1, int(round(rect.width() * dpr))),
                max(1, int(round(rect.height() * dpr))),
            )
            scaled = pixmap.scaled(
                hi_sz, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            scaled.setDevicePixelRatio(dpr)
            source_x = max(0, (scaled.width() - hi_sz.width()) // 2)
            source_y = max(0, (scaled.height() - hi_sz.height()) // 3)
            painter.drawPixmap(
                rect.topLeft(),
                scaled.copy(QRect(source_x, source_y, hi_sz.width(), hi_sz.height())),
            )

        if self._show_pill:
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
    selection_toggled = Signal(object, bool)

    def __init__(
        self,
        game: Game,
        selected: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.game = game
        self.setObjectName("card")
        self.setFixedWidth(188)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setProperty("hovered", False)

        body = QVBoxLayout(self)
        body.setContentsMargins(10, 10, 10, 10)
        body.setSpacing(6)

        self.cover = CoverArt(game, 168, 236, show_pill=False, radius=8.0)
        body.addWidget(self.cover, 0, Qt.AlignHCenter)

        self.title_label = QLabel(game.title)
        self.title_label.setObjectName("cardTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumHeight(44)
        body.addWidget(self.title_label)

        sub_parts = [game.subtitle or game.system]
        if game.playtime_seconds:
            sub_parts.append(game.playtime_text)
        self.subtitle_label = QLabel(" · ".join(part for part in sub_parts if part))
        self.subtitle_label.setObjectName("muted")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("font-size: 11.5px;")
        body.addWidget(self.subtitle_label)

        self.play_button = QPushButton("▶", self.cover)
        self.play_button.setObjectName("play")
        self.play_button.setCursor(Qt.PointingHandCursor)
        self.play_button.setFixedSize(34, 34)
        self.play_button.move(168 - 34 - 10, 236 - 34 - 10)
        self.play_button.clicked.connect(lambda: self.play_requested.emit(self.game))
        self.play_button.hide()
        self.play_button.raise_()

        from PySide6.QtWidgets import QCheckBox

        self.select_check = QCheckBox(self.cover)
        self.select_check.setCursor(Qt.PointingHandCursor)
        self.select_check.setFixedSize(22, 22)
        self.select_check.move(168 - 22 - 8, 8)
        self.select_check.setStyleSheet(
            "QCheckBox { background: rgba(12, 12, 16, 175); border-radius: 5px; padding: 2px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
        )
        self.select_check.setChecked(selected)
        self.select_check.setVisible(selected)
        self.select_check.toggled.connect(self._on_select_toggled)
        self.select_check.raise_()

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

    def _on_select_toggled(self, checked: bool) -> None:
        self.select_check.setVisible(checked or bool(self.property("hovered")))
        self.selection_toggled.emit(self.game, checked)

    def _set_hovered(self, hovered: bool) -> None:
        self.setProperty("hovered", hovered)
        self.style().unpolish(self)
        self.style().polish(self)
        self.play_button.setVisible(hovered)
        if hasattr(self, "select_check"):
            self.select_check.setVisible(hovered or self.select_check.isChecked())
        self._animation.stop()
        target_blur = 36 if hovered else 18
        if is_reduced_motion():
            self._shadow.setBlurRadius(target_blur)
        else:
            self._animation.setStartValue(self._shadow.blurRadius())
            self._animation.setEndValue(target_blur)
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
            self.play_requested.emit(self.game)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._details_timer.stop()
        self.context_requested.emit(self.game, event.globalPos())
        event.accept()


class SectionHeader(QWidget):
    def __init__(self, title: str, count_text: str = "", parent: Optional[QWidget] = None) -> None:
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
        if count_text:
            badge = QLabel(count_text)
            badge.setObjectName("tiny")
            badge.setStyleSheet(
                f"color: {active_style().muted}; background: rgba(255, 255, 255, 0.06);"
                " border-radius: 9px; padding: 2px 8px; font-weight: 600;"
            )
            row.addWidget(badge)
        row.addStretch(1)


class CardRow(QWidget):
    play_requested = Signal(object)
    details_requested = Signal(object)
    context_requested = Signal(object, object)
    selection_toggled = Signal(object, bool)

    def __init__(
        self,
        title: str,
        games: list[Game],
        selected_ids: Optional[set[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QScrollArea

        body = QVBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        body.addWidget(SectionHeader(title, count_text=str(len(games))))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFixedHeight(344)

        inner = QWidget()
        row = QHBoxLayout(inner)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        sel = selected_ids or set()
        for game in games:
            card = GameCard(game, selected=(game.id in sel))
            card.play_requested.connect(self.play_requested)
            card.details_requested.connect(self.details_requested)
            card.context_requested.connect(self.context_requested)
            card.selection_toggled.connect(self.selection_toggled)
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
        self.setFixedHeight(252)
        self.game: Optional[Game] = None
        self._backdrop_source: Optional[QPixmap] = None
        self._backdrop_cache: Optional[QPixmap] = None
        self._backdrop_key: tuple[str, int, int] = ("", 0, 0)
        self.setAttribute(Qt.WA_StyledBackground, False)

        body = QHBoxLayout(self)
        body.setContentsMargins(28, 22, 28, 22)
        body.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(6)
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
        self.description.setMaximumHeight(40)
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
            152,
            208,
            show_pill=False,
            radius=8.0,
        )
        self.cover.setVisible(False)
        body.addWidget(self.cover, 0, Qt.AlignVCenter)

    def set_game(self, game: Optional[Game]) -> None:
        self.game = game
        self._backdrop_source = None
        self._backdrop_cache = None
        self._backdrop_key = ("", 0, 0)
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

        from ..backdrops import game_backdrop
        from ..covers import game_cover

        cover_path = game_backdrop(game) or game_cover(game)
        if cover_path is not None:
            pix = QPixmap(str(cover_path))
            if not pix.isNull():
                self._backdrop_source = pix

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

    def _blurred_backdrop(self) -> Optional[QPixmap]:
        if self._backdrop_source is None or self._backdrop_source.isNull():
            return None
        key = (self.game.id if self.game else "", self.width(), self.height())
        if self._backdrop_cache is not None and self._backdrop_key == key:
            return self._backdrop_cache
        w = max(1, self.width())
        h = max(1, self.height())
        tiny_w = max(24, w // 18)
        tiny_h = max(16, h // 18)
        blurred = self._backdrop_source.scaled(
            tiny_w, tiny_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        ).scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self._backdrop_cache = blurred
        self._backdrop_key = key
        return blurred

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect().adjusted(0, 0, -1, -1)
        style = active_style()
        radius = max(10.0, float(style.radius))
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), radius, radius)
        painter.setClipPath(path)

        base = QLinearGradient(0, 0, self.width(), self.height())
        base.setColorAt(0.0, QColor(style.surface_2))
        base.setColorAt(0.65, QColor(style.surface))
        base.setColorAt(1.0, QColor(style.bg))
        painter.fillRect(rect, QBrush(base))

        backdrop = self._blurred_backdrop()
        if backdrop is not None:
            painter.setOpacity(0.32)
            sx = max(0, (backdrop.width() - self.width()) // 2)
            sy = max(0, (backdrop.height() - self.height()) // 3)
            painter.drawPixmap(0, 0, backdrop.copy(sx, sy, self.width(), self.height()))
            painter.setOpacity(1.0)
            scrim = QLinearGradient(0, 0, self.width(), 0)
            scrim_bg = QColor(style.bg)
            scrim.setColorAt(0.0, QColor(scrim_bg.red(), scrim_bg.green(), scrim_bg.blue(), 225))
            scrim.setColorAt(0.58, QColor(scrim_bg.red(), scrim_bg.green(), scrim_bg.blue(), 170))
            scrim.setColorAt(1.0, QColor(scrim_bg.red(), scrim_bg.green(), scrim_bg.blue(), 110))
            painter.fillRect(rect, QBrush(scrim))

        accent = QColor(style.accent)
        glow = QRadialGradient(self.width() * 0.82, self.height() * 0.45, self.width() * 0.55)
        glow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 38))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, QBrush(glow))

        painter.setClipping(False)
        border = QColor(style.accent)
        border.setAlpha(55)
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
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        body.addWidget(self.title_label)
        self.description_label = QLabel(description)
        self.description_label.setObjectName("muted")
        self.description_label.setAlignment(Qt.AlignCenter)
        self.description_label.setWordWrap(True)
        self.description_label.setFixedWidth(460)
        self.description_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
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
        target_w = self.description_label.width() or self.description_label.maximumWidth() or 460
        needed_h = self.description_label.heightForWidth(target_w)
        if needed_h > 0:
            self.description_label.setMinimumHeight(needed_h)
        self.description_label.adjustSize()
        self.description_label.updateGeometry()
        if self.button is not None:
            self.button.setVisible(bool(button_text))
            if button_text:
                self.button.setText(button_text)
        self.updateGeometry()


def apply_download_progress(bar: QProgressBar, done: int, total: int) -> str:
    """Update a progress bar (busy while total is 0, determinate 0-100 afterwards)."""
    from ..updater import format_download_progress

    if total > 0:
        percent = min(100, int(done * 100 / total))
        bar.setRange(0, 100)
        bar.setValue(percent)
        return format_download_progress(done, total)
    bar.setRange(0, 0)
    if done > 0:
        return format_download_progress(done, total)
    return "Solicitud recibida · conectando con GitHub…"


class UpdateBanner(QFrame):
    install_clicked = Signal()
    postpone_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateBannerShell")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(700)
        self._version = ""
        self._target = QPoint(0, 0)
        self._locked_height = 0
        self._last_parent_size: Optional[QSize] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        self._panel = QFrame()
        self._panel.setObjectName("updateBanner")
        outer.addWidget(self._panel)

        body = QVBoxLayout(self._panel)
        body.setContentsMargins(30, 26, 30, 26)
        body.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        badge = QLabel()
        icon_path = assets_dir() / "umbral.svg"
        if icon_path.exists():
            badge.setPixmap(
                QPixmap(str(icon_path)).scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            header.addWidget(badge)
        self.eyebrow = QLabel("ACTUALIZACIÓN DE UMBRAL")
        self.eyebrow.setObjectName("bannerEyebrow")
        header.addWidget(self.eyebrow)
        header.addStretch(1)
        body.addLayout(header)

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

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
        body.addWidget(self.progress_bar)

        body.addStretch(1)
        body.addSpacing(8)
        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.action = QPushButton("Actualizar ahora")
        self.action.setObjectName("bannerPrimary")
        self.action.setMinimumHeight(42)
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.clicked.connect(self.install_clicked)
        self.later = QPushButton("Ahora no")
        self.later.setObjectName("bannerGhost")
        self.later.setMinimumHeight(42)
        self.later.setCursor(Qt.PointingHandCursor)
        self.later.clicked.connect(self.postpone_clicked)
        actions.addWidget(self.action)
        actions.addWidget(self.later)
        actions.addStretch(1)
        body.addLayout(actions)
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        del event
        panel_rect = self._panel.geometry()
        if panel_rect.isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        for spread, alpha in ((18, 28), (13, 44), (8, 70), (4, 110)):
            shadow_rect = panel_rect.adjusted(-spread, -spread + 4, spread, spread + 8)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(shadow_rect, 4, 4)

    def current_version(self) -> str:
        return self._version

    def _lock_geometry_if_needed(self, reset: bool = False) -> None:
        if reset or self._locked_height <= 0:
            self.ensurePolished()
            self._panel.ensurePolished()
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            if self.layout() is not None:
                self.layout().activate()
            self.adjustSize()
            self._locked_height = max(self.height(), 328)
            self.setFixedHeight(self._locked_height)
            self._target = self._target_position()
            parent = self.parentWidget()
            self._last_parent_size = parent.size() if parent is not None else None
            self.move(self._target)

    def show_update(self, version: str, notes: str = "") -> None:
        self._version = version
        self.eyebrow.setText("ACTUALIZACIÓN DE UMBRAL")
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
        self.progress_bar.hide()
        self.action.setText("Actualizar ahora")
        self.action.setEnabled(True)
        self.later.setEnabled(True)
        self.later.show()
        self._lock_geometry_if_needed(reset=True)
        self.show()
        self.raise_()

    def show_progress(self, done: int, total: int) -> None:
        self._lock_geometry_if_needed()
        self.eyebrow.setText("DESCARGANDO ACTUALIZACIÓN")
        self.line1.hide()
        self.line2.hide()
        if total > 0:
            percent = min(100, int(done * 100 / total))
            self.title.setText(f"Descargando Umbral {self._version}…")
            self.action.setText(f"Descargando… {percent} %")
        elif done > 0:
            self.title.setText(f"Descargando Umbral {self._version}…")
            self.action.setText("Descargando…")
        else:
            self.title.setText(f"Iniciando actualización a {self._version}…")
            self.action.setText("Conectando…")
        self.detail.setText(apply_download_progress(self.progress_bar, done, total))
        self.detail.show()
        self.progress_bar.show()
        self.action.setEnabled(False)
        self.later.setEnabled(False)
        if not self.isVisible():
            self.move(self._target)
            self.show()
        self.raise_()

    def show_installing(self) -> None:
        self._lock_geometry_if_needed()
        self.eyebrow.setText("APLICANDO ACTUALIZACIÓN")
        self.line1.hide()
        self.line2.hide()
        self.title.setText(f"Instalando Umbral {self._version}…")
        self.detail.setText("Descarga completada · cerrando Umbral para actualizar y reiniciar…")
        self.detail.show()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.show()
        self.action.setText("Instalando…")
        self.action.setEnabled(False)
        self.later.setEnabled(False)
        if not self.isVisible():
            self.move(self._target)
            self.show()
        self.raise_()

    def show_error(self, message: str) -> None:
        self._lock_geometry_if_needed()
        self.eyebrow.setText("ERROR DE ACTUALIZACIÓN")
        self.title.setText("No se pudo actualizar")
        self.line1.hide()
        self.line2.hide()
        self.progress_bar.hide()
        self.detail.setText(message)
        self.detail.show()
        self.action.setText("Reintentar")
        self.action.setEnabled(True)
        self.later.setEnabled(True)
        if not self.isVisible():
            self.move(self._target)
            self.show()
        self.raise_()

    def reposition(self) -> None:
        if not self.isVisible():
            return
        parent = self.parentWidget()
        current_size = parent.size() if parent is not None else None
        if current_size is not None and current_size == self._last_parent_size:
            return
        self._last_parent_size = current_size
        self._target = self._target_position()
        self.move(self._target)

    def _target_position(self) -> QPoint:
        parent = self.parentWidget()
        if parent is None:
            return QPoint(0, 0)
        x = max(18, (parent.width() - self.width()) // 2)
        y = max(18, (parent.height() - self.height()) // 2 - 20)
        return QPoint(x, y)


class Toast(QLabel):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignCenter)
        self.hide()
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._animation = QPropertyAnimation(self._effect, b"opacity", self)
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.finished.connect(self._on_animation_finished)
        self._slide_anim = QPropertyAnimation(self, b"pos", self)
        self._slide_anim.setDuration(200)
        self._slide_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def show_message(self, text: str, milliseconds: int = 3400) -> None:
        self.setText(text)
        self.adjustSize()
        self._animation.stop()
        self._slide_anim.stop()
        parent = self.parentWidget()
        target = (
            QPoint(parent.width() - self.width() - 28, parent.height() - self.height() - 28)
            if parent
            else QPoint(0, 0)
        )
        self.show()
        self.raise_()
        if is_reduced_motion():
            self.move(target)
            self._effect.setOpacity(1.0)
        else:
            self.move(target.x(), target.y() + 12)
            self._effect.setOpacity(0.0)
            self._slide_anim.setStartValue(self.pos())
            self._slide_anim.setEndValue(target)
            self._slide_anim.start()
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(1.0)
            self._animation.start()
        self._timer.start(milliseconds)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent:
            self.move(parent.width() - self.width() - 28, parent.height() - self.height() - 28)

    def _fade_out(self) -> None:
        if is_reduced_motion():
            self._effect.setOpacity(0.0)
            self.hide()
            return
        self._animation.stop()
        self._animation.setStartValue(self._effect.opacity())
        self._animation.setEndValue(0.0)
        self._animation.start()

    def _on_animation_finished(self) -> None:
        if self._effect.opacity() <= 0.01:
            self.hide()


class UmbralButton(QPushButton):
    """QPushButton with vector icon tinting, smooth hover/press sheen, and loading state."""

    def __init__(
        self,
        text: str = "",
        icon_name: str = "",
        icon_size: int = 15,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self._base_text = text
        self._icon_name = icon_name
        self._icon_size = icon_size
        self._hovered = False
        self._pressed = False
        self._hover_progress = 0.0
        self._press_progress = 0.0
        self._loading = False
        self._spin_angle = 0.0

        self.setAttribute(Qt.WA_Hover, True)
        if icon_name:
            self.setIconSize(QSize(icon_size, icon_size))
        self._hover_anim = QPropertyAnimation(self, b"hover_progress", self)
        self._hover_anim.setDuration(140)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._press_anim = QPropertyAnimation(self, b"press_progress", self)
        self._press_anim.setDuration(90)
        self._press_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(40)
        self._spin_timer.timeout.connect(self._advance_spinner)
        self.refresh_icon()

    def _get_hover_progress(self) -> float:
        return self._hover_progress

    def _set_hover_progress(self, value: float) -> None:
        self._hover_progress = float(value)
        self.update()

    hover_progress = property(_get_hover_progress, _set_hover_progress)  # type: ignore[assignment]

    def _get_press_progress(self) -> float:
        return self._press_progress

    def _set_press_progress(self, value: float) -> None:
        self._press_progress = float(value)
        self.update()

    press_progress = property(_get_press_progress, _set_press_progress)  # type: ignore[assignment]

    def set_icon_name(self, icon_name: str) -> None:
        self._icon_name = icon_name
        if icon_name:
            self.setIconSize(QSize(self._icon_size, self._icon_size))
        self.refresh_icon()

    def refresh_icon(self) -> None:
        style = active_style()
        name = "spinner" if self._loading else self._icon_name
        if not name:
            self.setIcon(vector_icon("", style.text, self._icon_size))
            return
        if self.objectName() == "primary":
            color = style.accent_2
        elif self._hovered and not self._loading:
            color = style.accent_2
        elif self._loading:
            color = style.accent
        else:
            color = style.text
        angle = self._spin_angle if self._loading else 0.0
        self.setIcon(vector_icon(name, color, size=self._icon_size, angle=angle))

    def set_loading(self, loading: bool, label: str = "") -> None:
        loading = bool(loading)
        if loading == self._loading:
            if loading and label:
                self.setText(label)
            return
        self._loading = loading
        if loading:
            self._base_text = self.text()
            if label:
                self.setText(label)
            self.setEnabled(False)
            self.setIconSize(QSize(self._icon_size, self._icon_size))
            if not is_reduced_motion():
                self._spin_timer.start()
        else:
            self._spin_timer.stop()
            self._spin_angle = 0.0
            self.setText(self._base_text)
            self.setEnabled(True)
        self.refresh_icon()

    def _advance_spinner(self) -> None:
        self._spin_angle = (self._spin_angle + 24.0) % 360.0
        self.refresh_icon()

    def _animate_hover(self, target: float) -> None:
        self._hover_anim.stop()
        if is_reduced_motion():
            self._hover_progress = target
            self.update()
            return
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(target)
        self._hover_anim.start()

    def _animate_press(self, target: float) -> None:
        self._press_anim.stop()
        if is_reduced_motion():
            self._press_progress = target
            self.update()
            return
        self._press_anim.setStartValue(self._press_progress)
        self._press_anim.setEndValue(target)
        self._press_anim.start()

    def enterEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._hovered = True
        self.refresh_icon()
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._hovered = False
        self._pressed = False
        self.refresh_icon()
        self._animate_hover(0.0)
        self._animate_press(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._pressed = True
            self._animate_press(1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._pressed = False
        self._animate_press(0.0)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().paintEvent(event)
        if self._hover_progress <= 0.01 and self._press_progress <= 0.01:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        style = active_style()
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = float(max(4, style.radius))
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        painter.setClipPath(clip)
        if self._hover_progress > 0.01 and self.isEnabled():
            sheen = QColor(style.accent_2)
            sheen.setAlpha(int(24 * self._hover_progress))
            top_grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
            top_grad.setColorAt(0.0, sheen)
            top_grad.setColorAt(0.65, QColor(0, 0, 0, 0))
            painter.fillRect(rect, QBrush(top_grad))
        if self._press_progress > 0.01:
            shade = QColor(0, 0, 0, int(45 * self._press_progress))
            painter.fillRect(rect, shade)
        painter.end()


class StylePreview(QFrame):
    clicked = Signal(str)

    def __init__(self, style, selected: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.style = style
        self.selected = selected
        self._hovered = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(196, 78)
        self.setAttribute(Qt.WA_Hover, True)

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
        painter.drawText(QRect(14, 16, rect.width() - 28, 24), Qt.AlignLeft | Qt.AlignVCenter, style.name)

        swatches = [style.accent, style.accent_2, style.success, style.danger]
        for index, color in enumerate(swatches):
            chip = QRect(14 + index * 18, 50, 12, 7)
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


class StartupOverlay(QWidget):
    """Animated intro: half-diamond brackets swallow 'UMBRAL' and reveal the glowing inner diamond."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._elapsed_ms = 0
        self._total_ms = 2550
        self._start_ts = 0.0
        self._bg_cache: Optional[QPixmap] = None
        self._bg_cache_key: tuple = ()
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        import time

        self._elapsed_ms = 0
        self._start_ts = time.monotonic()
        self.show()
        self.raise_()
        self._timer.start()

    def _tick(self) -> None:
        import time

        if self._start_ts > 0.0:
            self._elapsed_ms = int((time.monotonic() - self._start_ts) * 1000.0)
        else:
            self._elapsed_ms += 20
        if self._elapsed_ms >= self._total_ms:
            self._timer.stop()
            self.hide()
            self.deleteLater()
            return
        self.update()

    @staticmethod
    def _ease_in_out_cubic(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return 4 * t * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2

    def _ensure_bg_cache(self, w: int, h: int, style) -> QPixmap:
        key = (w, h, style.key)
        if self._bg_cache is not None and self._bg_cache_key == key:
            return self._bg_cache
        pix = QPixmap(max(1, w), max(1, h))
        pix.fill(Qt.black)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        accent = QColor(style.accent)
        cx, cy = w * 0.5, h * 0.48
        bg_grad = QLinearGradient(0.0, 0.0, float(w), float(h))
        bg_grad.setColorAt(0.0, QColor("#070604"))
        bg_grad.setColorAt(0.55, QColor(style.bg))
        bg_grad.setColorAt(1.0, QColor(accent.red() // 6, accent.green() // 6, accent.blue() // 8))
        p.fillRect(pix.rect(), QBrush(bg_grad))
        amb = QRadialGradient(cx, cy, max(w, h) * 0.42)
        amb.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 44))
        amb.setColorAt(0.55, QColor(accent.red(), accent.green(), accent.blue(), 14))
        amb.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(pix.rect(), QBrush(amb))
        p.end()
        self._bg_cache = pix
        self._bg_cache_key = key
        return pix

    def paintEvent(self, event) -> None:
        t = float(self._elapsed_ms)
        fade_out = 1.0
        if t > 2150.0:
            fade_out = max(0.0, 1.0 - self._ease_in_out_cubic((t - 2150.0) / 400.0))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setOpacity(fade_out)

        style = active_style()
        w, h = float(self.width()), float(self.height())
        cx, cy = w * 0.5, h * 0.48
        accent = QColor(style.accent)
        accent_2 = QColor(style.accent_2)

        bg_pix = self._ensure_bg_cache(self.width(), self.height(), style)
        painter.drawPixmap(0, 0, bg_pix)

        # Typography measurement for "UMBRAL"
        title_font = QFont(style.heading_font or "Cinzel")
        title_font.setPixelSize(64)
        title_font.setWeight(QFont.DemiBold)
        title_font.setLetterSpacing(QFont.AbsoluteSpacing, 12.0)
        fm = QFontMetrics(title_font)
        text = "UMBRAL"
        text_w = float(fm.horizontalAdvance(text))

        # Sharper, larger outer diamond geometry (acute mitered tips)
        half_w = 42.0
        half_h = 84.0
        spread = text_w * 0.5 + 48.0

        # Phase 1: 0..1000ms hold; Phase 2: 1000..1650ms close brackets
        close_p = 0.0 if t <= 1000.0 else self._ease_in_out_cubic((t - 1000.0) / 650.0)
        offset = spread * (1.0 - close_p)

        # Draw "UMBRAL" clipped strictly between the two closing half-diamond inner edges
        clip_half = max(0.0, offset)
        if clip_half > 1.0:
            painter.save()
            clip_rect = QRectF(cx - clip_half, cy - 64.0, clip_half * 2.0, 128.0)
            painter.setClipRect(clip_rect)
            painter.setFont(title_font)
            painter.setPen(accent_2)
            painter.drawText(QRectF(cx - text_w, cy - 52.0, text_w * 2.0, 104.0), Qt.AlignCenter, text)
            painter.restore()

        # Draw sharp left (<) and right (>) half-diamond brackets; when joined, draw a single closed diamond
        painter.setBrush(Qt.NoBrush)
        if offset <= 0.6:
            pen = QPen(accent, 4.4, Qt.SolidLine, Qt.RoundCap, Qt.MiterJoin)
            pen.setMiterLimit(4.0)
            painter.setPen(pen)
            closed = QPainterPath()
            closed.moveTo(cx, cy - half_h)
            closed.lineTo(cx + half_w, cy)
            closed.lineTo(cx, cy + half_h)
            closed.lineTo(cx - half_w, cy)
            closed.closeSubpath()
            painter.drawPath(closed)
        else:
            pen = QPen(accent, 4.4, Qt.SolidLine, Qt.RoundCap, Qt.MiterJoin)
            painter.setPen(pen)

            left_path = QPainterPath()
            left_path.moveTo(cx - offset, cy - half_h)
            left_path.lineTo(cx - offset - half_w, cy)
            left_path.lineTo(cx - offset, cy + half_h)
            painter.drawPath(left_path)

            right_path = QPainterPath()
            right_path.moveTo(cx + offset, cy - half_h)
            right_path.lineTo(cx + offset + half_w, cy)
            right_path.lineTo(cx + offset, cy + half_h)
            painter.drawPath(right_path)

        # Subtitle "Gonzalo Sanjurjo" below
        sub_font = QFont(style.heading_font or "Cinzel")
        sub_font.setPixelSize(16)
        sub_font.setLetterSpacing(QFont.AbsoluteSpacing, 5.5)
        painter.setFont(sub_font)
        sub_color = QColor(accent_2)
        sub_color.setAlpha(205)
        painter.setPen(sub_color)
        painter.drawText(
            QRectF(0.0, cy + half_h + 26.0, w, 34.0),
            Qt.AlignHCenter | Qt.AlignTop,
            "Gonzalo Sanjurjo",
        )

        # Phase 3: 1600..2150ms inner golden diamond appears & glows
        if t > 1600.0:
            glow_p = self._ease_in_out_cubic((t - 1600.0) / 480.0)
            bloom_r = 34.0 + 68.0 * glow_p
            bloom = QRadialGradient(cx, cy, bloom_r)
            bloom_alpha = int(175 * glow_p * (1.15 - 0.35 * glow_p))
            bloom.setColorAt(0.0, QColor(accent_2.red(), accent_2.green(), accent_2.blue(), min(255, bloom_alpha)))
            bloom.setColorAt(0.45, QColor(accent.red(), accent.green(), accent.blue(), int(bloom_alpha * 0.55)))
            bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(bloom))
            painter.drawEllipse(QPointF(cx, cy), bloom_r, bloom_r)

            in_w = 16.5 * (0.65 + 0.35 * glow_p)
            in_h = 38.0 * (0.65 + 0.35 * glow_p)
            inner_diamond = QPainterPath()
            inner_diamond.moveTo(cx, cy - in_h)
            inner_diamond.lineTo(cx + in_w, cy)
            inner_diamond.lineTo(cx, cy + in_h)
            inner_diamond.lineTo(cx - in_w, cy)
            inner_diamond.closeSubpath()
            fill = QColor(accent)
            fill.setAlpha(int(255 * glow_p))
            painter.setBrush(fill)
            painter.drawPath(inner_diamond)

