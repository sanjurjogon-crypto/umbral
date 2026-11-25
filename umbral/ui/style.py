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
    name="Umbral Clásico",
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
    radius=4,
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

OBSIDIAN_STYLE = GameStyle(
    key="obsidian",
    name="Obsidiana Minimal",
    game="Minimal",
    blurb="Pizarra oscura y azul hielo.",
    bg="#090c12",
    surface="#10151f",
    surface_2="#161d2b",
    surface_3="#1d2638",
    border="#29354d",
    border_soft="#1b2333",
    text="#e2e8f0",
    muted="#94a3b8",
    muted_2="#64748b",
    accent="#7dd3fc",
    accent_2="#e0f2fe",
    danger="#f87171",
    success="#4ade80",
    info="#60a5fa",
    heading_font="Bahnschrift",
    body_font="Segoe UI",
    heading_weight=600,
    heading_spacing=1.5,
    uppercase_headings=False,
    radius=8,
    border_width=1,
    sidebar="#0c1018",
    sidebar_2="#090c12",
    canvas="#07090e",
    motif="stardust",
    backdrop_top="#111a2b",
    backdrop_bottom="#05070b",
    motif_color="#7dd3fc",
    ember_color="#bae6fd",
)

NEON_STYLE = GameStyle(
    key="neon",
    name="Neón Arcade",
    game="Arcade",
    blurb="Noche ciberpunk, magenta y cian.",
    bg="#0b0714",
    surface="#130d21",
    surface_2="#1b122e",
    surface_3="#24193d",
    border="#45276b",
    border_soft="#2b1945",
    text="#f3e8ff",
    muted="#b794d4",
    muted_2="#7b5ba1",
    accent="#ff3e9d",
    accent_2="#22d3ee",
    danger="#fb7185",
    success="#34d399",
    info="#38bdf8",
    heading_font="Bahnschrift",
    body_font="Segoe UI",
    heading_weight=700,
    heading_spacing=2.2,
    uppercase_headings=True,
    radius=6,
    border_width=1,
    sidebar="#0e091a",
    sidebar_2="#0b0714",
    canvas="#07040d",
    motif="grid",
    backdrop_top="#1c0d30",
    backdrop_bottom="#05030a",
    motif_color="#ff3e9d",
    ember_color="#22d3ee",
)

FOREST_STYLE = GameStyle(
    key="forest",
    name="Bosque Antiguo",
    game="Bosque",
    blurb="Esmeralda profunda y pergamino.",
    bg="#070d0a",
    surface="#0d1712",
    surface_2="#122119",
    surface_3="#192c22",
    border="#264736",
    border_soft="#192e23",
    text="#e2efe7",
    muted="#8fb59f",
    muted_2="#5d7f6c",
    accent="#34d399",
    accent_2="#d1fae5",
    danger="#ef4444",
    success="#6ee7b7",
    info="#67e8f9",
    heading_font="Cinzel",
    body_font="EB Garamond",
    heading_weight=600,
    heading_spacing=2.0,
    uppercase_headings=False,
    radius=4,
    border_width=1,
    sidebar="#09110d",
    sidebar_2="#070d0a",
    canvas="#050907",
    motif="golddust",
    backdrop_top="#0e2017",
    backdrop_bottom="#040705",
    motif_color="#34d399",
    ember_color="#a7f3d0",
)

STYLES: tuple[GameStyle, ...] = (UMBRAL_STYLE, OBSIDIAN_STYLE, NEON_STYLE, FOREST_STYLE)
STYLE_BY_KEY: dict[str, GameStyle] = {style.key: style for style in STYLES}
DEFAULT_STYLE = UMBRAL_STYLE.key

_active: GameStyle = UMBRAL_STYLE


def set_active(key: str | None) -> GameStyle:
    global _active
    _active = style_for(key)
    return _active


def active() -> GameStyle:
    return _active


def style_for(key: str | None) -> GameStyle:
    return STYLE_BY_KEY.get(str(key or "").strip().lower(), UMBRAL_STYLE)


def is_dark(style: GameStyle) -> bool:
    value = style.bg.lstrip("#")
    if len(value) != 6:
        return True
    red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    return (0.299 * red + 0.587 * green + 0.114 * blue) < 128
