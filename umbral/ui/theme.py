from __future__ import annotations

from PySide6.QtGui import QColor

from .style import STYLES, GameStyle, style_for

BG = "#080705"
SURFACE = "#100e0a"
SURFACE_2 = "#17140e"
SURFACE_3 = "#1f1a12"
BORDER = "#3b3223"
BORDER_SOFT = "#241f16"
TEXT = "#ded2b8"
MUTED = "#9c9077"
MUTED_2 = "#6d6350"
DANGER = "#a64036"
SUCCESS = "#8b9a72"
WARNING = "#c9a45f"
INFO = "#93a1ae"

ACCENTS = [
    (style.name, style.accent) for style in STYLES
]


def _rgba(color: str, alpha: float) -> str:
    value = QColor(color)
    if not value.isValid():
        value = QColor(WARNING)
    return f"rgba({value.red()}, {value.green()}, {value.blue()}, {alpha})"


def _mix(first: str, second: str, amount: float) -> str:
    left = QColor(first)
    right = QColor(second)
    amount = max(0.0, min(1.0, amount))
    return QColor(
        int(left.red() + (right.red() - left.red()) * amount),
        int(left.green() + (right.green() - left.green()) * amount),
        int(left.blue() + (right.blue() - left.blue()) * amount),
    ).name()


def qss(accent: str | None = None, style_key: str | None = None) -> str:
    style = style_for(style_key)
    accent = accent or style.accent
    soft = _rgba(accent, 0.14)
    softer = _rgba(accent, 0.06)
    border_accent = _rgba(accent, 0.55)
    glow = _rgba(accent, 0.35)
    hover_bg = _rgba(style.text, 0.05)
    scroll = _mix(style.border, style.bg, 0.45)
    input_bg = _mix(style.bg, style.surface, 0.6)
    radius = style.radius
    thin = style.border_width
    heading = style.heading_font
    body = style.body_font
    spacing = style.heading_spacing
    weight = style.heading_weight
    transform = "text-transform: uppercase;" if style.uppercase_headings else ""
    template = """
    QWidget {
        font-family: "__BODY__", "Palatino Linotype", serif;
        font-size: 14px;
        color: __TEXT__;
    }
    QMainWindow, QWidget#root, QDialog {
        background: __BG__;
    }
    QLabel {
        background: transparent;
    }
    QLabel#muted {
        color: __MUTED__;
    }
    QLabel#tiny {
        color: __MUTED_2__;
        font-size: 11px;
        letter-spacing: 1px;
        __TRANSFORM__
    }
    QLabel#h1 {
        font-family: "__HEADING__";
        font-size: 31px;
        font-weight: __WEIGHT__;
        letter-spacing: __SPACING__px;
        __TRANSFORM__
    }
    QLabel#h2 {
        font-family: "__HEADING__";
        font-size: 22px;
        font-weight: __WEIGHT__;
        letter-spacing: __SPACING__px;
        __TRANSFORM__
    }
    QLabel#heroTitle {
        font-family: "__HEADING__";
        font-size: 33px;
        font-weight: __WEIGHT__;
        letter-spacing: __SPACING__px;
        __TRANSFORM__
    }
    QLabel#sectionTitle {
        font-family: "__HEADING__";
        font-size: 17px;
        font-weight: __WEIGHT__;
        letter-spacing: __SPACING__px;
        __TRANSFORM__
    }
    QLabel#kicker {
        color: __ACCENT__;
        font-family: "__HEADING__";
        font-size: 11px;
        font-weight: __WEIGHT__;
        letter-spacing: 4px;
        __TRANSFORM__
    }
    QLabel#statValue {
        color: __ACCENT__;
        font-family: "__HEADING__";
        font-size: 27px;
        font-weight: __WEIGHT__;
        letter-spacing: 1px;
    }
    QLabel#statLabel {
        color: __MUTED__;
        font-size: 12px;
        letter-spacing: 2px;
    }
    QLabel#brandName {
        font-family: "__HEADING__";
        font-size: 20px;
        font-weight: __WEIGHT__;
        letter-spacing: 4px;
        color: __ACCENT_2__;
        __TRANSFORM__
    }
    QFrame#sidebar {
        background: rgba(10, 9, 7, 0.62);
        border-right: __THIN__px solid __BORDER__;
    }
    QFrame#topbar {
        background: transparent;
        border: none;
    }
    QScrollArea#sidebarScroll {
        background: transparent;
        border: none;
    }
    QWidget#sidebarContent {
        background: transparent;
    }
    QFrame#navIndicator, QFrame#sysIndicator {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 __ACCENT_SOFT__, stop:1 rgba(0, 0, 0, 0));
        border-left: 2px solid __ACCENT__;
        border-radius: __RADIUS__px;
    }
    QFrame#accentBar {
        background: __ACCENT__;
        border-radius: __RADIUS__px;
    }
    QFrame#card, QFrame#tile, QFrame#health {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 __SURFACE_2__, stop:1 __SURFACE__);
        border: __THIN__px solid __BORDER__;
        border-radius: __RADIUS__px;
    }
    QFrame#card[hovered="true"] {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 __SURFACE_3__, stop:1 __SURFACE_2__);
        border: __THIN__px solid __BORDER_ACCENT__;
    }
    QFrame#divider {
        background: __BORDER__;
        max-height: 1px;
        min-height: 1px;
        border: none;
    }
    QPushButton {
        background: transparent;
        border: none;
        border-radius: __RADIUS__px;
        padding: 8px 12px;
        color: __TEXT__;
        text-align: left;
    }
    QPushButton:hover {
        color: __ACCENT_2__;
    }
    QPushButton:pressed {
        color: __ACCENT__;
    }
    QPushButton#primary {
        background: __SOFTER__;
        border: __THIN__px solid __ACCENT__;
        color: __ACCENT_2__;
        font-family: "__HEADING__";
        font-size: 12px;
        font-weight: __WEIGHT__;
        letter-spacing: 2px;
        padding: 10px 22px;
        border-radius: __RADIUS__px;
        text-align: center;
        __TRANSFORM__
    }
    QPushButton#primary:hover {
        background: __ACCENT_SOFT__;
        color: __ACCENT_2__;
    }
    QPushButton#primary:pressed {
        background: __ACCENT_SOFTER__;
    }
    QPushButton#ghost {
        border: __THIN__px solid __BORDER__;
        background: transparent;
        padding: 9px 18px;
        color: __MUTED__;
        font-family: "__HEADING__";
        font-size: 12px;
        letter-spacing: 1.5px;
        text-align: center;
        border-radius: __RADIUS__px;
        __TRANSFORM__
    }
    QPushButton#ghost:hover {
        border-color: __ACCENT__;
        color: __ACCENT__;
    }
    QPushButton#danger {
        border: __THIN__px solid __DANGER__;
        color: __DANGER__;
        padding: 9px 16px;
        font-family: "__HEADING__";
        font-size: 12px;
        letter-spacing: 1px;
        border-radius: __RADIUS__px;
    }
    QPushButton#nav {
        background: transparent;
        text-align: left;
        padding: 11px 14px;
        border-radius: __RADIUS__px;
        border-left: 2px solid transparent;
        color: __MUTED__;
        font-family: "__HEADING__";
        font-size: 12px;
        font-weight: __WEIGHT__;
        letter-spacing: 1.5px;
        __TRANSFORM__
    }
    QPushButton#nav:hover {
        color: __TEXT__;
        background: __HOVER_BG__;
    }
    QPushButton#nav:checked {
        background: transparent;
        color: __ACCENT_2__;
        border-left: 2px solid transparent;
    }
    QPushButton#system {
        background: transparent;
        text-align: left;
        padding: 7px 14px;
        border-radius: __RADIUS__px;
        border-left: 2px solid transparent;
        color: __MUTED__;
        font-size: 13px;
    }
    QPushButton#system:hover {
        color: __TEXT__;
        background: __HOVER_BG__;
    }
    QPushButton#system:checked {
        color: __ACCENT_2__;
        background: transparent;
        border-left: 2px solid transparent;
    }
    QPushButton#chip {
        border: __THIN__px solid __BORDER__;
        border-radius: __RADIUS__px;
        padding: 6px 15px;
        color: __MUTED__;
        font-family: "__HEADING__";
        font-size: 11px;
        letter-spacing: 1px;
        text-align: center;
        __TRANSFORM__
    }
    QPushButton#chip:hover {
        border-color: __BORDER_ACCENT__;
        color: __TEXT__;
    }
    QPushButton#chip:checked {
        background: __ACCENT_SOFT__;
        border-color: __ACCENT__;
        color: __ACCENT_2__;
    }
    QPushButton#icon {
        border: __THIN__px solid __BORDER__;
        border-radius: __RADIUS__px;
        padding: 6px 12px;
        text-align: center;
        font-size: 12px;
        letter-spacing: 1px;
    }
    QPushButton#icon:hover {
        border-color: __ACCENT__;
        color: __ACCENT__;
    }
    QPushButton#swatch {
        border: 2px solid transparent;
        border-radius: __RADIUS__px;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
    }
    QPushButton#swatch:checked {
        border: 2px solid __TEXT__;
    }
    QLabel#cardTitle {
        font-family: "__HEADING__";
        font-size: 13px;
        font-weight: __WEIGHT__;
        letter-spacing: 1px;
        color: __ACCENT_2__;
        __TRANSFORM__
    }
    QPushButton#play {
        background: __SOFTER__;
        color: __ACCENT_2__;
        border: __THIN__px solid __ACCENT__;
        border-radius: __RADIUS__px;
        font-size: 12px;
        text-align: center;
    }
    QPushButton#play:hover {
        background: __ACCENT__;
        color: __BG__;
    }
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {
        background: __INPUT_BG__;
        border: __THIN__px solid __BORDER__;
        border-radius: __RADIUS__px;
        padding: 8px 12px;
        color: __TEXT__;
        selection-background-color: __ACCENT__;
        selection-color: __BG__;
    }
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {
        border: __THIN__px solid __ACCENT__;
    }
    QLineEdit::placeholder {
        color: __MUTED_2__;
    }
    QComboBox::drop-down {
        border: none;
        width: 26px;
    }
    QComboBox QAbstractItemView {
        background: __SURFACE_2__;
        border: __THIN__px solid __BORDER__;
        selection-background-color: __ACCENT_SOFT__;
        selection-color: __ACCENT_2__;
        outline: none;
    }
    QMenu {
        background: __SURFACE_2__;
        border: __THIN__px solid __BORDER__;
        padding: 4px;
    }
    QMenu::item {
        padding: 7px 18px;
        color: __TEXT__;
        border-radius: __RADIUS__px;
    }
    QMenu::item:selected {
        background: __ACCENT_SOFT__;
        color: __ACCENT_2__;
    }
    QMenu::separator {
        height: 1px;
        background: __BORDER_SOFT__;
        margin: 4px 8px;
    }
    QScrollArea {
        border: none;
        background: transparent;
    }
    QScrollArea > QWidget > QWidget {
        background: transparent;
    }
    QScrollBar:vertical {
        background: transparent;
        width: 8px;
        margin: 2px;
    }
    QScrollBar::handle:vertical {
        background: __SCROLL__;
        min-height: 32px;
        border-radius: __RADIUS__px;
    }
    QScrollBar::handle:vertical:hover {
        background: __ACCENT__;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
    QScrollBar:horizontal {
        background: transparent;
        height: 8px;
        margin: 2px;
    }
    QScrollBar::handle:horizontal {
        background: __SCROLL__;
        min-width: 32px;
        border-radius: __RADIUS__px;
    }
    QScrollBar::handle:horizontal:hover {
        background: __ACCENT__;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0;
    }
    QToolTip {
        background: __SURFACE_2__;
        color: __TEXT__;
        border: __THIN__px solid __BORDER__;
        padding: 6px 9px;
        border-radius: __RADIUS__px;
    }
    QProgressBar {
        border: none;
        background: __SURFACE_3__;
        border-radius: __RADIUS__px;
        min-height: 6px;
        max-height: 6px;
    }
    QProgressBar::chunk {
        background: __ACCENT__;
        border-radius: __RADIUS__px;
    }
    QLabel#toast {
        background: __SURFACE_2__;
        border: __THIN__px solid __BORDER_ACCENT__;
        border-radius: __RADIUS__px;
        padding: 10px 20px;
        color: __ACCENT_2__;
        font-family: "__HEADING__";
        font-size: 12px;
        letter-spacing: 1px;
    }
    QWidget#shelfHeader {
        background: transparent;
    }
    QLabel#shelfWord {
        font-family: "__HEADING__";
        font-size: 30px;
        font-weight: __WEIGHT__;
        letter-spacing: 4px;
        color: __ACCENT_2__;
        __TRANSFORM__
    }
    QLabel#shelfCount {
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 4px;
        color: __MUTED_2__;
    }
    QWidget#tabs {
        background: transparent;
        border: none;
    }
    QPushButton#shelfTab {
        border: none;
        border-bottom: 1px solid transparent;
        border-radius: 0px;
        padding: 6px 12px;
        font-family: "__HEADING__";
        font-size: 11px;
        font-weight: __WEIGHT__;
        letter-spacing: 1.5px;
        color: __MUTED__;
        background: transparent;
        text-align: center;
        __TRANSFORM__
    }
    QPushButton#shelfTab:hover {
        color: __TEXT__;
    }
    QPushButton#shelfTab:checked {
        color: __ACCENT_2__;
        border-bottom: 1px solid __ACCENT__;
    }
    QWidget#shelfCanvas {
        background: __CANVAS__;
    }
    QLabel#shelfTitle {
        font-family: "__HEADING__";
        font-size: 29px;
        font-weight: __WEIGHT__;
        letter-spacing: 2px;
        color: __ACCENT_2__;
        padding: 3px 0;
        __TRANSFORM__
    }
    QLabel#shelfMeta {
        font-size: 12px;
        letter-spacing: 2px;
        color: __MUTED__;
    }
    QLabel#shelfHint {
        font-size: 11px;
        letter-spacing: 1px;
        color: __MUTED_2__;
        padding: 6px 0 14px 0;
        background: transparent;
    }
    QWidget#shelfInfo {
        background: transparent;
    }
    QMessageBox {
        background: __SURFACE__;
    }
    QCheckBox {
        spacing: 9px;
        color: __TEXT__;
    }
    QCheckBox::indicator {
        width: 14px;
        height: 14px;
        border: 1px solid __BORDER__;
        background: __INPUT_BG__;
    }
    QCheckBox::indicator:hover {
        border-color: __ACCENT__;
    }
    QCheckBox::indicator:checked {
        background: __ACCENT__;
        border-color: __ACCENT__;
    }
    """
    replacements = {
        "__BODY__": body,
        "__HEADING__": heading,
        "__WEIGHT__": str(weight),
        "__SPACING__": f"{spacing:g}",
        "__TRANSFORM__": transform,
        "__RADIUS__": str(radius),
        "__THIN__": str(thin),
        "__BG__": style.bg,
        "__SURFACE__": style.surface,
        "__SURFACE_2__": style.surface_2,
        "__SURFACE_3__": style.surface_3,
        "__BORDER__": style.border,
        "__BORDER_SOFT__": style.border_soft,
        "__BORDER_ACCENT__": border_accent,
        "__TEXT__": style.text,
        "__MUTED__": style.muted,
        "__MUTED_2__": style.muted_2,
        "__DANGER__": style.danger,
        "__SUCCESS__": style.success,
        "__INFO__": style.info,
        "__ACCENT_LIGHT__": QColor(accent).lighter(118).name(),
        "__ACCENT_2__": style.accent_2,
        "__ACCENT_SOFT__": soft,
        "__ACCENT_SOFTER__": softer,
        "__ACCENT__": accent,
        "__GLOW__": glow,
        "__SOFT__": soft,
        "__SOFTER__": softer,
        "__HOVER_BG__": hover_bg,
        "__SCROLL__": scroll,
        "__INPUT_BG__": input_bg,
        "__SIDEBAR__": style.sidebar,
        "__SIDEBAR_2__": style.sidebar_2,
        "__CANVAS__": style.canvas,
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def style_title(key: str | None) -> str:
    return style_for(key).name
