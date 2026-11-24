from __future__ import annotations

from PySide6.QtGui import QColor

from ..paths import assets_dir
from .style import GameStyle


def _rgba(color: str, alpha: float) -> str:
    value = QColor(color)
    if not value.isValid():
        value = QColor("#c9a45f")
    return f"rgba({value.red()}, {value.green()}, {value.blue()}, {alpha})"


def extra_qss(style: GameStyle) -> str:
    accent = style.accent
    accent_2 = style.accent_2
    radius = style.radius
    thin = style.border_width
    heading = style.heading_font
    weight = style.heading_weight
    transform = "text-transform: uppercase;" if style.uppercase_headings else ""
    soft = _rgba(accent, 0.16)
    softer = _rgba(accent, 0.07)
    hair = _rgba(accent, 0.5)
    chevron = (assets_dir() / "chevron.svg").as_posix()
    return f"""
    QPushButton#primary {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {style.surface_3}, stop:0.45 {softer}, stop:1 {style.bg});
        border: {thin}px solid {accent};
        border-bottom: 2px solid {hair};
        color: {accent_2};
        font-family: "{heading}";
        font-size: 12px;
        font-weight: {weight};
        letter-spacing: 2px;
        padding: 10px 24px;
        border-radius: {radius}px;
        text-align: center;
        {transform}
    }}
    QPushButton#primary:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {soft}, stop:1 {style.surface});
        border-color: {accent_2};
    }}
    QPushButton#primary:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {style.bg}, stop:1 {style.surface_2});
        border-bottom-color: {accent};
    }}
    QPushButton#ghost {{
        background: rgba(14, 12, 10, 0.44);
        border: {thin}px solid rgba(255, 255, 255, 0.14);
        border-bottom: 2px solid {style.border_soft};
        color: {style.muted};
        padding: 9px 18px;
        font-family: "{heading}";
        font-size: 12px;
        letter-spacing: 1.5px;
        border-radius: {radius}px;
        {transform}
    }}
    QPushButton#ghost:hover {{
        background: {softer};
        border-color: {accent};
        color: {accent};
    }}
    QPushButton#chip {{
        background: rgba(14, 12, 10, 0.44);
        border: {thin}px solid rgba(255, 255, 255, 0.14);
        border-bottom: 2px solid {style.border_soft};
        color: {style.muted};
        padding: 6px 16px;
        border-radius: {radius}px;
        font-family: "{heading}";
        font-size: 11px;
        letter-spacing: 1px;
        {transform}
    }}
    QPushButton#chip:hover {{
        color: {style.text};
        border-color: {hair};
    }}
    QPushButton#chip:checked {{
        background: rgba(212, 175, 55, 0.18);
        border-color: {accent};
        color: {accent_2};
        border-bottom: 2px solid {accent};
    }}
    QPushButton#shelfTab {{
        border: none;
        border-bottom: 2px solid transparent;
        padding: 7px 13px 6px 13px;
        background: transparent;
        color: {style.muted};
        font-family: "{heading}";
        font-size: 11px;
        font-weight: {weight};
        letter-spacing: 1.6px;
        {transform}
    }}
    QPushButton#shelfTab:hover {{
        color: {style.text};
        border-bottom-color: {hair};
    }}
    QPushButton#shelfTab:checked {{
        color: {accent_2};
        border-bottom: 2px solid {accent};
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {softer}, stop:1 transparent);
    }}
    QPushButton#nav {{
        border-left: 2px solid transparent;
        border-bottom: 1px solid transparent;
        background: transparent;
    }}
    QPushButton#nav:hover {{
        border-bottom-color: rgba(255, 255, 255, 0.08);
        background: rgba(255, 255, 255, 0.05);
    }}
    QPushButton#nav:checked {{
        border-left: 2px solid transparent;
        border-bottom: 1px solid transparent;
        background: transparent;
        color: {accent_2};
    }}
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {{
        background: rgba(12, 11, 9, 0.48);
        border: {thin}px solid rgba(255, 255, 255, 0.14);
        border-top: 2px solid rgba(255, 255, 255, 0.08);
        border-radius: {radius}px;
        padding: 8px 12px;
        color: {style.text};
        selection-background-color: {accent};
        selection-color: {style.bg};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: {thin}px solid {accent};
        border-top: 2px solid {accent};
        background: rgba(16, 14, 11, 0.65);
    }}
    QFrame#sidebar {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(10, 9, 7, 0.72), stop:0.85 rgba(10, 9, 7, 0.56), stop:1 rgba(10, 9, 7, 0.46));
        border-right: 1px solid {hair};
    }}
    QLabel#toast {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(20, 18, 14, 0.78), stop:1 rgba(10, 9, 7, 0.72));
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-left: 3px solid {accent};
        border-radius: {radius}px;
        padding: 10px 22px;
        color: {accent_2};
        font-family: "{heading}";
        font-size: 12px;
        letter-spacing: 1px;
    }}
    QFrame#updateBanner {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(22, 19, 14, 0.90), stop:0.45 rgba(14, 12, 10, 0.86), stop:1 rgba(8, 8, 7, 0.90));
        border: {thin}px solid rgba(255, 255, 255, 0.14);
        border-top: 2px solid {accent};
        border-bottom: 1px solid {hair};
        border-radius: {radius}px;
    }}
    QLabel#bannerEyebrow {{
        color: {accent};
        font-family: "{heading}";
        font-size: 11px;
        font-weight: {weight};
        letter-spacing: 2.5px;
    }}
    QLabel#bannerTitle {{
        color: {accent_2};
        font-family: "{heading}";
        font-size: 21px;
        font-weight: {weight};
        letter-spacing: 0.4px;
    }}
    QLabel#bannerText {{
        color: {style.text};
        font-size: 16px;
    }}
    QLabel#bannerDetail {{
        color: {accent};
        font-size: 13px;
        letter-spacing: 0.6px;
    }}
    QPushButton#bannerPrimary {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(212, 175, 55, 0.28), stop:1 rgba(212, 175, 55, 0.14));
        border: {thin}px solid {accent};
        border-bottom: 2px solid {hair};
        color: {accent_2};
        font-family: "{heading}";
        font-size: 12px;
        font-weight: {weight};
        letter-spacing: 1.8px;
        padding: 10px 24px;
        border-radius: {radius}px;
    }}
    QPushButton#bannerPrimary:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(212, 175, 55, 0.40), stop:1 rgba(212, 175, 55, 0.22));
        border-color: {accent_2};
    }}
    QPushButton#bannerGhost {{
        background: rgba(14, 12, 10, 0.52);
        border: {thin}px solid rgba(255, 255, 255, 0.14);
        border-bottom: 2px solid {style.border_soft};
        color: {style.muted};
        font-family: "{heading}";
        font-size: 12px;
        letter-spacing: 1.4px;
        padding: 10px 20px;
        border-radius: {radius}px;
    }}
    QPushButton#bannerGhost:hover {{
        background: {softer};
        border-color: {accent};
        color: {accent_2};
    }}
    QPushButton#bannerLink {{
        background: transparent;
        border: none;
        color: {accent};
        font-size: 11px;
        letter-spacing: 0.5px;
        padding: 4px 0px;
        text-align: left;
    }}
    QPushButton#bannerLink:hover {{
        color: {accent_2};
    }}
    QFrame#card, QFrame#tile, QFrame#health {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {style.surface_2}, stop:1 {style.surface});
        border: {thin}px solid {style.border};
        border-top: 2px solid {hair};
        border-radius: {radius}px;
    }}
    QProgressBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {style.bg}, stop:1 {style.surface_3});
        border: 1px solid {style.border};
        border-radius: {radius}px;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {accent_2}, stop:1 {accent});
        border-radius: {radius}px;
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {style.border}, stop:1 {style.border_soft});
        border-radius: {radius}px;
    }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {accent};
    }}
    QComboBox {{
        padding: 8px 34px 8px 12px;
        background: rgba(12, 11, 9, 0.48);
        border: {thin}px solid rgba(255, 255, 255, 0.14);
        color: {style.text};
    }}
    QComboBox:hover {{
        border: {thin}px solid {hair};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 30px;
        border-left: 1px solid {style.border_soft};
    }}
    QComboBox::down-arrow {{
        image: url("{chevron}");
        width: 12px;
        height: 8px;
    }}
    QComboBox QAbstractItemView {{
        background: {style.surface};
        border: {thin}px solid {hair};
        padding: 4px;
        outline: none;
        selection-background-color: {soft};
        selection-color: {accent_2};
    }}
    QComboBox QAbstractItemView::item {{
        padding: 8px 12px;
        min-height: 20px;
        color: {style.text};
    }}
    QComboBox QAbstractItemView::item:selected {{
        background: {soft};
        color: {accent_2};
    }}
    QLabel#styleSeal {{
        color: {accent_2};
        background: {softer};
        border: {thin}px solid {hair};
        border-radius: {radius}px;
        padding: 4px 10px;
        font-family: "{heading}";
        font-size: 9px;
        font-weight: {weight};
        letter-spacing: 2px;
        text-transform: uppercase;
    }}
    """
