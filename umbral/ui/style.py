from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GameStyle:
    key: str
    name: str
    game: str
    blurb: str
    bg: str
    surface: str
    surface_2: str
    surface_3: str
    border: str
    border_soft: str
    text: str
    muted: str
    muted_2: str
    accent: str
    accent_2: str
    danger: str
    success: str
    info: str
    heading_font: str
    body_font: str
    heading_weight: int
    heading_spacing: float
    uppercase_headings: bool
    radius: int
    border_width: int
    sidebar: str
    sidebar_2: str
    canvas: str
    motif: str
    backdrop_top: str
    backdrop_bottom: str
    motif_color: str
    ember_color: str


UMBRAL_STYLE = GameStyle(
    key="umbral",
    name="Oro y ébano",
    game="Umbral",
    blurb="Negro profundo y oro viejo.",
    bg="#080807",
    surface="#100f0c",
    surface_2="#16140f",
    surface_3="#1e1b13",
    border="#3a3423",
    border_soft="#241f15",
    text="#e8dfc8",
    muted="#a2977c",
    muted_2="#6f6753",
    accent="#d4af37",
    accent_2="#efe0b4",
    danger="#a64036",
    success="#8b9a72",
    info="#8c99a6",
    heading_font="Cinzel",
    body_font="EB Garamond",
    heading_weight=600,
    heading_spacing=2.0,
    uppercase_headings=False,
    radius=0,
    border_width=1,
    sidebar="#0b0a08",
    sidebar_2="#080807",
    canvas="#060605",
    motif="golddust",
    backdrop_top="#151309",
    backdrop_bottom="#040403",
    motif_color="#d4af37",
    ember_color="#e2c46a",
)

STYLES: tuple[GameStyle, ...] = (UMBRAL_STYLE,)
STYLE_BY_KEY: dict[str, GameStyle] = {UMBRAL_STYLE.key: UMBRAL_STYLE}
DEFAULT_STYLE = UMBRAL_STYLE.key

_active: GameStyle = UMBRAL_STYLE


def set_active(key: str | None) -> GameStyle:
    global _active
    _active = style_for(key)
    return _active


def active() -> GameStyle:
    return _active


def style_for(key: str | None) -> GameStyle:
    return UMBRAL_STYLE


def is_dark(style: GameStyle) -> bool:
    value = style.bg.lstrip("#")
    if len(value) != 6:
        return True
    red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    return (0.299 * red + 0.587 * green + 0.114 * blue) < 128
