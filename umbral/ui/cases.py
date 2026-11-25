from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
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
    QPolygonF,
    QRadialGradient,
    QTransform,
)

from ..consoles import SYSTEM_LABELS
from ..models import Game
from ..paths import assets_dir
from ..profiles import PROFILES
from ..rom_rules import path_hint, rom_system
from .style import active as active_style

EMULATOR_COLORS: dict[str, str] = {profile.key: profile.accent for profile in PROFILES}
EMULATOR_NAMES: dict[str, str] = {profile.key: profile.name for profile in PROFILES}
EMULATOR_BY_NAME: dict[str, str] = {
    profile.name.lower(): profile.key for profile in PROFILES
}

PC_BAND = "#17130d"
PC_BAND_LIGHT = "#2a2317"
SANS_FONT = "Segoe UI"
NINTENDO_FONT = "Bahnschrift"
PS_FONT = "Trebuchet MS"
XBOX_FONT = "Segoe UI"
HEADLINE_FONT = "Arial Black"


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
    shell_kind: str = "keepcase"  # translucent_clear | translucent_tint | keepcase | jewel_clear | cardboard | pc_keepcase
    shell_color: str = "#1a1f28"
    shell_alpha: int = 235
    bezel: tuple[float, float, float, float] = (0.024, 0.022, 0.024, 0.022)


CASE_PROFILES: dict[str, CaseProfile] = {
    "switch2": CaseProfile(
        key="switch2",
        w_scale=1.08,
        h_scale=0.95,
        radius=5.5,
        spine_color="#e60012",
        header_bg="#e60012",
        header_accent="#ff5a5f",
        header_text="#ffffff",
        band_label="SWITCH 2",
        depth_scale=1.05,
        shell_kind="template",
        shell_color="#e60012",
        shell_alpha=245,
        bezel=(0.032, 0.026, 0.032, 0.026),
    ),
    "switch": CaseProfile(
        key="switch",
        w_scale=0.84,
        h_scale=1.01,
        radius=5.5,
        spine_color="#e60012",
        header_bg="#e60012",
        header_accent="#ff6b6b",
        header_text="#ffffff",
        band_label="SWITCH",
        depth_scale=0.72,
        shell_kind="translucent_clear",
        shell_color="#cfd9e3",
        shell_alpha=155,
        bezel=(0.026, 0.022, 0.026, 0.022),
    ),
    "3ds": CaseProfile(
        key="3ds",
        w_scale=1.18,
        h_scale=0.77,
        radius=6.0,
        spine_color="#eef1f5",
        header_bg="#f6f7f9",
        header_accent="#d32f2f",
        header_text="#17191c",
        band_label="NINTENDO 3DS",
        depth_scale=0.95,
        shell_kind="template",
        shell_color="#f3f5f8",
        shell_alpha=255,
        bezel=(0.024, 0.026, 0.024, 0.026),
    ),
    "nds": CaseProfile(
        key="nds",
        w_scale=0.96,
        h_scale=0.80,
        radius=5.0,
        spine_color="#949eab",
        header_bg="#eceff3",
        header_accent="#64748b",
        header_text="#181b20",
        band_label="NINTENDO DS",
        depth_scale=0.95,
        shell_kind="translucent_clear",
        shell_color="#9da8b6",
        shell_alpha=178,
        bezel=(0.028, 0.028, 0.028, 0.028),
    ),
    "wii": CaseProfile(
        key="wii",
        w_scale=0.90,
        h_scale=1.01,
        radius=5.5,
        spine_color="#eef2f6",
        header_bg="#f8fafc",
        header_accent="#009ac7",
        header_text="#64748b",
        band_label="WII",
        depth_scale=0.90,
        shell_kind="keepcase",
        shell_color="#f2f5f8",
        shell_alpha=255,
        bezel=(0.025, 0.022, 0.025, 0.022),
    ),
    "wiiu": CaseProfile(
        key="wiiu",
        w_scale=0.90,
        h_scale=1.01,
        radius=5.5,
        spine_color="#009ac7",
        header_bg="#009ac7",
        header_accent="#67e8f9",
        header_text="#ffffff",
        band_label="WII U",
        depth_scale=0.90,
        shell_kind="translucent_tint",
        shell_color="#009ac7",
        shell_alpha=225,
        bezel=(0.026, 0.022, 0.026, 0.022),
    ),
    "gamecube": CaseProfile(
        key="gamecube",
        w_scale=0.90,
        h_scale=1.01,
        radius=5.0,
        spine_color="#1d1e24",
        header_bg="#101116",
        header_accent="#6959cd",
        header_text="#ffffff",
        band_label="GAMECUBE",
        depth_scale=0.90,
        shell_kind="keepcase",
        shell_color="#1c1d22",
        shell_alpha=255,
        bezel=(0.025, 0.022, 0.025, 0.022),
    ),
    "ps3": CaseProfile(
        key="ps3",
        w_scale=0.88,
        h_scale=0.95,
        radius=6.0,
        spine_color="#232833",
        header_bg="#0b0d12",
        header_accent="#c2cde0",
        header_text="#f2f5fa",
        band_label="PLAYSTATION 3",
        depth_scale=0.82,
        shell_kind="translucent_clear",
        shell_color="#cbd5e1",
        shell_alpha=145,
        bezel=(0.024, 0.044, 0.024, 0.020),
    ),
    "ps2": CaseProfile(
        key="ps2",
        w_scale=0.91,
        h_scale=1.01,
        radius=4.5,
        spine_color="#113684",
        header_bg="#07090d",
        header_accent="#3b82f6",
        header_text="#f3f6ff",
        band_label="PLAYSTATION 2",
        depth_scale=0.92,
        shell_kind="translucent_tint",
        shell_color="#133a8d",
        shell_alpha=232,
        bezel=(0.026, 0.022, 0.026, 0.022),
    ),
    "ps1": CaseProfile(
        key="ps1",
        w_scale=0.99,
        h_scale=0.84,
        radius=3.0,
        spine_color="#343840",
        header_bg="#08090c",
        header_accent="#9ca3af",
        header_text="#f8fafc",
        band_label="PLAYSTATION",
        depth_scale=0.86,
        shell_kind="jewel_clear",
        shell_color="#c8d1dc",
        shell_alpha=165,
        bezel=(0.020, 0.020, 0.020, 0.020),
    ),
    "psp": CaseProfile(
        key="psp",
        w_scale=0.77,
        h_scale=1.02,
        radius=7.5,
        spine_color="#c6d0db",
        header_bg="#0d1016",
        header_accent="#7dd3fc",
        header_text="#f8fafc",
        band_label="PSP",
        depth_scale=0.76,
        shell_kind="translucent_clear",
        shell_color="#d7e0ea",
        shell_alpha=155,
        bezel=(0.030, 0.026, 0.030, 0.026),
    ),
    "psvita": CaseProfile(
        key="psvita",
        w_scale=0.80,
        h_scale=0.95,
        radius=6.0,
        spine_color="#0052cc",
        header_bg="#0044b3",
        header_accent="#38bdf8",
        header_text="#ffffff",
        band_label="PS VITA",
        depth_scale=0.74,
        shell_kind="translucent_tint",
        shell_color="#0055d4",
        shell_alpha=225,
        bezel=(0.028, 0.024, 0.028, 0.024),
    ),
    "xbox360": CaseProfile(
        key="xbox360",
        w_scale=0.91,
        h_scale=1.01,
        radius=5.0,
        spine_color="#2a8a24",
        header_bg="#f2f5f7",
        header_accent="#7ed321",
        header_text="#182018",
        band_label="XBOX 360",
        depth_scale=0.92,
        shell_kind="translucent_tint",
        shell_color="#2a8f24",
        shell_alpha=215,
        bezel=(0.026, 0.022, 0.026, 0.022),
    ),
    "xbox": CaseProfile(
        key="xbox",
        w_scale=0.91,
        h_scale=1.01,
        radius=5.0,
        spine_color="#176d17",
        header_bg="#0a320a",
        header_accent="#65d82e",
        header_text="#ffffff",
        band_label="XBOX",
        depth_scale=0.92,
        shell_kind="translucent_tint",
        shell_color="#1d7e1d",
        shell_alpha=220,
        bezel=(0.026, 0.022, 0.026, 0.022),
    ),
    "dreamcast": CaseProfile(
        key="dreamcast",
        w_scale=0.99,
        h_scale=0.84,
        radius=3.5,
        spine_color="#004eb0",
        header_bg="#004cb3",
        header_accent="#60a5fa",
        header_text="#ffffff",
        band_label="DREAMCAST",
        depth_scale=0.88,
        shell_kind="jewel_clear",
        shell_color="#b8cde6",
        shell_alpha=165,
        bezel=(0.020, 0.020, 0.020, 0.020),
    ),
    "saturn": CaseProfile(
        key="saturn",
        w_scale=0.85,
        h_scale=1.04,
        radius=3.5,
        spine_color="#12141a",
        header_bg="#0e1015",
        header_accent="#3b82f6",
        header_text="#f8fafc",
        band_label="SEGA SATURN",
        depth_scale=0.88,
        shell_kind="keepcase",
        shell_color="#13161d",
        shell_alpha=255,
        bezel=(0.024, 0.022, 0.024, 0.022),
    ),
    "n64": CaseProfile(
        key="n64",
        w_scale=1.02,
        h_scale=0.76,
        radius=3.0,
        spine_color="#14161a",
        header_bg="#0e1014",
        header_accent="#e11d48",
        header_text="#ffffff",
        band_label="NINTENDO 64",
        depth_scale=0.96,
        shell_kind="cardboard",
        shell_color="#111317",
        shell_alpha=255,
        bezel=(0.022, 0.024, 0.022, 0.024),
    ),
    "snes": CaseProfile(
        key="snes",
        w_scale=1.02,
        h_scale=0.76,
        radius=3.0,
        spine_color="#17191e",
        header_bg="#101216",
        header_accent="#cbd5e1",
        header_text="#f8fafc",
        band_label="SUPER NINTENDO",
        depth_scale=0.96,
        shell_kind="cardboard",
        shell_color="#14161a",
        shell_alpha=255,
        bezel=(0.022, 0.024, 0.022, 0.024),
    ),
    "nes": CaseProfile(
        key="nes",
        w_scale=0.84,
        h_scale=1.02,
        radius=2.5,
        spine_color="#141518",
        header_bg="#111216",
        header_accent="#e11d48",
        header_text="#f8fafc",
        band_label="NES",
        depth_scale=0.95,
        shell_kind="cardboard",
        shell_color="#141518",
        shell_alpha=255,
        bezel=(0.020, 0.020, 0.020, 0.020),
    ),
    "gba": CaseProfile(
        key="gba",
        w_scale=0.94,
        h_scale=0.94,
        radius=3.0,
        spine_color="#4b2e91",
        header_bg="#3d247a",
        header_accent="#a78bfa",
        header_text="#ffffff",
        band_label="GAME BOY ADVANCE",
        depth_scale=0.92,
        shell_kind="cardboard",
        shell_color="#452988",
        shell_alpha=255,
        bezel=(0.018, 0.018, 0.018, 0.018),
    ),
    "gbc": CaseProfile(
        key="gbc",
        w_scale=0.94,
        h_scale=0.94,
        radius=3.0,
        spine_color="#7c3aed",
        header_bg="#4c1d95",
        header_accent="#fbbf24",
        header_text="#ffffff",
        band_label="GAME BOY COLOR",
        depth_scale=0.92,
        shell_kind="cardboard",
        shell_color="#b8bec8",
        shell_alpha=255,
        bezel=(0.018, 0.018, 0.018, 0.018),
    ),
    "gb": CaseProfile(
        key="gb",
        w_scale=0.94,
        h_scale=0.94,
        radius=3.0,
        spine_color="#8e94a0",
        header_bg="#bfc4ce",
        header_accent="#3b4ba8",
        header_text="#182038",
        band_label="GAME BOY",
        depth_scale=0.92,
        shell_kind="cardboard",
        shell_color="#bfc4ce",
        shell_alpha=255,
        bezel=(0.018, 0.018, 0.018, 0.018),
    ),
    "genesis": CaseProfile(
        key="genesis",
        w_scale=0.86,
        h_scale=1.04,
        radius=4.0,
        spine_color="#111317",
        header_bg="#0c0d11",
        header_accent="#ef4444",
        header_text="#f8fafc",
        band_label="MEGA DRIVE",
        depth_scale=0.94,
        shell_kind="keepcase",
        shell_color="#14161b",
        shell_alpha=255,
        bezel=(0.022, 0.020, 0.022, 0.020),
    ),
    "mastersystem": CaseProfile(
        key="mastersystem",
        w_scale=0.86,
        h_scale=1.04,
        radius=4.0,
        spine_color="#eef0f3",
        header_bg="#f3f5f8",
        header_accent="#dc2626",
        header_text="#111827",
        band_label="MASTER SYSTEM",
        depth_scale=0.94,
        shell_kind="keepcase",
        shell_color="#eceff4",
        shell_alpha=255,
        bezel=(0.022, 0.020, 0.022, 0.020),
    ),
    "gamegear": CaseProfile(
        key="gamegear",
        w_scale=0.92,
        h_scale=0.96,
        radius=3.0,
        spine_color="#1e1b3a",
        header_bg="#181530",
        header_accent="#38bdf8",
        header_text="#f8fafc",
        band_label="GAME GEAR",
        depth_scale=0.90,
        shell_kind="cardboard",
        shell_color="#191632",
        shell_alpha=255,
        bezel=(0.018, 0.018, 0.018, 0.018),
    ),
    "neogeo": CaseProfile(
        key="neogeo",
        w_scale=0.84,
        h_scale=1.05,
        radius=4.0,
        spine_color="#151310",
        header_bg="#11100d",
        header_accent="#d4af37",
        header_text="#f7e3a1",
        band_label="NEO GEO",
        depth_scale=0.98,
        shell_kind="keepcase",
        shell_color="#171512",
        shell_alpha=255,
        bezel=(0.022, 0.020, 0.022, 0.020),
    ),
    "arcade": CaseProfile(
        key="arcade",
        w_scale=0.94,
        h_scale=0.98,
        radius=4.0,
        spine_color="#1d2436",
        header_bg="#121826",
        header_accent="#f59e0b",
        header_text="#fef3c7",
        band_label="ARCADE",
        depth_scale=0.92,
        shell_kind="keepcase",
        shell_color="#161b29",
        shell_alpha=255,
        bezel=(0.020, 0.020, 0.020, 0.020),
    ),
    "pce": CaseProfile(
        key="pce",
        w_scale=0.98,
        h_scale=0.84,
        radius=3.0,
        spine_color="#23252c",
        header_bg="#121318",
        header_accent="#fb923c",
        header_text="#fff7ed",
        band_label="PC ENGINE",
        depth_scale=0.78,
        shell_kind="jewel_clear",
        shell_color="#c2cad4",
        shell_alpha=165,
        bezel=(0.020, 0.020, 0.020, 0.020),
    ),
    "ports": CaseProfile(
        key="ports",
        w_scale=0.90,
        h_scale=1.00,
        radius=4.5,
        spine_color="#2a2214",
        header_bg="#19150d",
        header_accent="#d4af37",
        header_text="#efe0b4",
        band_label="PORT",
        depth_scale=0.95,
        shell_kind="pc_keepcase",
        shell_color="#19150d",
        shell_alpha=255,
        bezel=(0.0, 0.0, 0.0, 0.0),
    ),
    "dusklight": CaseProfile(
        key="dusklight",
        w_scale=1.08,
        h_scale=0.95,
        radius=5.5,
        spine_color="#1a1714",
        header_bg="#14110f",
        header_accent="#d97706",
        header_text="#fef3c7",
        band_label="DUSKLIGHT",
        depth_scale=1.05,
        shell_kind="template",
        shell_color="#14110f",
        shell_alpha=255,
        bezel=(0.0, 0.0, 0.0, 0.0),
    ),
    "hookshot": CaseProfile(
        key="hookshot",
        w_scale=0.955,
        h_scale=1.00,
        radius=5.5,
        spine_color="#0e2240",
        header_bg="#0b1a33",
        header_accent="#60a5fa",
        header_text="#f8fafc",
        band_label="HOOKSHOT",
        depth_scale=0.98,
        shell_kind="template",
        shell_color="#0b1a33",
        shell_alpha=255,
        bezel=(0.0, 0.0, 0.0, 0.0),
    ),
    "longshot": CaseProfile(
        key="longshot",
        w_scale=0.955,
        h_scale=1.00,
        radius=5.5,
        spine_color="#2a1640",
        header_bg="#1d0f2e",
        header_accent="#c084fc",
        header_text="#faf5ff",
        band_label="LONGSHOT",
        depth_scale=0.98,
        shell_kind="template",
        shell_color="#1d0f2e",
        shell_alpha=255,
        bezel=(0.0, 0.0, 0.0, 0.0),
    ),
    "steam": CaseProfile(
        key="steam",
        w_scale=1.00,
        h_scale=0.945,
        radius=5.5,
        spine_color="#0c1522",
        header_bg="#0a121d",
        header_accent="#66c0f4",
        header_text="#e5e9f0",
        band_label="STEAM",
        depth_scale=1.00,
        shell_kind="template",
        shell_color="#0a121d",
        shell_alpha=255,
        bezel=(0.0, 0.0, 0.0, 0.0),
    ),
    "epic": CaseProfile(
        key="epic",
        w_scale=0.96,
        h_scale=0.96,
        radius=5.5,
        spine_color="#161124",
        header_bg="#120e1e",
        header_accent="#a855f7",
        header_text="#f3e8ff",
        band_label="EPIC GAMES",
        depth_scale=0.92,
        shell_kind="template",
        shell_color="#120e1e",
        shell_alpha=255,
        bezel=(0.0, 0.0, 0.0, 0.0),
    ),
    "gog": CaseProfile(
        key="gog",
        w_scale=0.90,
        h_scale=1.00,
        radius=4.5,
        spine_color="#181b20",
        header_bg="#14171c",
        header_accent="#b77bff",
        header_text="#e5e9f0",
        band_label="GOG",
        depth_scale=0.95,
        shell_kind="pc_keepcase",
        shell_color="#14171c",
        shell_alpha=255,
        bezel=(0.0, 0.0, 0.0, 0.0),
    ),
    "pc": CaseProfile(
        key="pc",
        w_scale=1.02,
        h_scale=0.95,
        radius=5.5,
        spine_color="#0e2240",
        header_bg="#0b1a33",
        header_accent="#38bdf8",
        header_text="#e5e9f0",
        band_label="PC",
        depth_scale=0.95,
        shell_kind="template",
        shell_color="#0b1a33",
        shell_alpha=255,
        bezel=(0.0, 0.0, 0.0, 0.0),
    ),
}


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def _emulator_key(game: Game) -> str:
    name = (game.emulator or "").strip().lower()
    return EMULATOR_BY_NAME.get(name, "") if name else ""


def is_pc_case(game: Game) -> bool:
    source = (game.source or "").strip().lower()
    sys_key = (game.system_key or "").strip().lower()
    if sys_key in {"pc", "steam", "epic", "gog"} or source in {"steam", "epic", "gog"}:
        return True
    return sys_key == "" and (game.emulator or "").strip().lower() in {"standalone", ""}


def _band_color(game: Game) -> QColor:
    if is_pc_case(game):
        return QColor(PC_BAND)
    key = _emulator_key(game)
    color = QColor(EMULATOR_COLORS.get(key, game.accent or "#E9B949"))
    if not color.isValid():
        color = QColor("#E9B949")
    return color


def _band_text(game: Game) -> str:
    if is_pc_case(game):
        return "PC"
    sys_key = (game.system_key or "").strip().lower()
    if sys_key in SYSTEM_LABELS:
        return SYSTEM_LABELS[sys_key]
    key = _emulator_key(game)
    if key and key in EMULATOR_NAMES:
        return EMULATOR_NAMES[key]
    return game.system or game.emulator or "RETRO"


def _effective_system_key(game: Game) -> str:
    sys_key = (game.system_key or "").strip().lower()
    if sys_key == "wii" and game.rom_path:
        rom = Path(game.rom_path)
        suffix = rom.suffix.lower()
        if suffix in {".gcm", ".gcz"} or path_hint(rom) == "gamecube":
            return "gamecube"
        if suffix in {".iso", ".rvz"} and rom.is_file():
            detected = rom_system(rom)
            if detected == "gamecube":
                return "gamecube"
    return sys_key


def case_profile(game: Game) -> CaseProfile:
    """Return physical box dimensions and European PAL styling for a game."""
    port_hint = f"{game.title} {game.emulator} {game.executable}".lower()
    for port_key in ("dusklight", "hookshot", "longshot"):
        if port_key in port_hint:
            return CASE_PROFILES[port_key]
    source = (game.source or "").strip().lower()
    sys_key = _effective_system_key(game)
    if sys_key in CASE_PROFILES and sys_key not in {"pc", "ports"}:
        return CASE_PROFILES[sys_key]
    if source in CASE_PROFILES:
        return CASE_PROFILES[source]
    if sys_key in CASE_PROFILES:
        return CASE_PROFILES[sys_key]
    if not is_pc_case(game):
        band_col = _band_color(game)
        return CaseProfile(
            key=sys_key or "retro",
            w_scale=0.92,
            h_scale=0.98,
            radius=3.5,
            spine_color=band_col.darker(155).name(),
            header_bg=band_col.darker(175).name(),
            header_accent=band_col.name(),
            header_text="#f5f7fb",
            band_label=_band_text(game).upper(),
            depth_scale=0.9,
            shell_kind="cardboard",
            shell_color=band_col.darker(190).name(),
            shell_alpha=255,
            bezel=(0.020, 0.020, 0.020, 0.020),
        )
    return CASE_PROFILES["pc"]


def console_art_rect(frame: QRectF, profile: CaseProfile) -> QRectF:
    """Return the exact printed artwork sleeve rectangle for a physical console case."""
    w, h = frame.width(), frame.height()
    bl, bt, br, bb = profile.bezel
    inner = QRectF(
        frame.left() + w * bl,
        frame.top() + h * bt,
        max(16.0, w * (1.0 - bl - br)),
        max(16.0, h * (1.0 - bt - bb)),
    )
    key = profile.key
    if key == "switch2":
        top_cut = inner.height() * 0.145
        return inner.adjusted(0.0, top_cut, 0.0, 0.0)
    if key == "switch":
        return inner
    if key == "3ds":
        strip_w = inner.width() * 0.145
        return QRectF(inner.left(), inner.top(), inner.width() - strip_w, inner.height())
    if key == "nds":
        strip_w = inner.width() * 0.135
        return QRectF(inner.left() + strip_w, inner.top(), inner.width() - strip_w, inner.height())
    if key in {"wii", "wiiu"}:
        return inner.adjusted(0.0, inner.height() * 0.115, 0.0, 0.0)
    if key == "gamecube":
        return inner.adjusted(0.0, inner.height() * 0.145, 0.0, 0.0)
    if key == "ps3":
        return inner.adjusted(0.0, inner.height() * 0.118, 0.0, 0.0)
    if key == "ps2":
        return inner.adjusted(0.0, inner.height() * 0.125, 0.0, 0.0)
    if key == "ps1":
        hinge_w = inner.width() * 0.105
        bottom_h = inner.height() * 0.132
        return QRectF(
            inner.left() + hinge_w,
            inner.top(),
            inner.width() - hinge_w,
            inner.height() - bottom_h,
        )
    if key == "psp":
        return inner.adjusted(0.0, inner.height() * 0.122, 0.0, 0.0)
    if key == "psvita":
        return inner.adjusted(0.0, inner.height() * 0.125, 0.0, 0.0)
    if key in {"xbox", "xbox360"}:
        return inner.adjusted(0.0, inner.height() * 0.128, 0.0, 0.0)
    if key == "dreamcast":
        hinge_w = inner.width() * 0.095
        top_h = inner.height() * 0.145
        return QRectF(
            inner.left() + hinge_w,
            inner.top() + top_h,
            inner.width() - hinge_w,
            inner.height() - top_h,
        )
    if key == "saturn":
        return inner.adjusted(inner.width() * 0.11, inner.height() * 0.09, -inner.width() * 0.03, -inner.height() * 0.03)
    if key == "n64":
        return inner.adjusted(inner.width() * 0.045, inner.height() * 0.14, -inner.width() * 0.045, -inner.height() * 0.045)
    if key == "snes":
        return inner.adjusted(inner.width() * 0.045, inner.height() * 0.145, -inner.width() * 0.045, -inner.height() * 0.045)
    if key == "nes":
        return inner.adjusted(inner.width() * 0.05, inner.height() * 0.125, -inner.width() * 0.05, -inner.height() * 0.05)
    if key in {"gb", "gbc", "gba"}:
        return inner.adjusted(inner.width() * 0.145, inner.height() * 0.04, -inner.width() * 0.04, -inner.height() * 0.04)
    if key in {"genesis", "mastersystem", "gamegear"}:
        return inner.adjusted(inner.width() * 0.045, inner.height() * 0.135, -inner.width() * 0.045, -inner.height() * 0.045)
    if key == "neogeo":
        return inner.adjusted(inner.width() * 0.05, inner.height() * 0.125, -inner.width() * 0.05, -inner.height() * 0.05)
    if key == "pce":
        hinge_w = inner.width() * 0.09
        return QRectF(
            inner.left() + hinge_w,
            inner.top() + inner.height() * 0.115,
            inner.width() - hinge_w,
            inner.height() * 0.885,
        )
    return inner.adjusted(0.0, inner.height() * 0.12, 0.0, 0.0)


def _draw_cover_art(painter: QPainter, rect: QRectF, pixmap: Optional[QPixmap]) -> None:
    if pixmap is None or pixmap.isNull():
        return
    src_size = QSize(max(1, int(round(rect.width()))), max(1, int(round(rect.height()))))
    ratio = pixmap.width() / max(1, pixmap.height())
    target_ratio = rect.width() / max(1.0, rect.height())
    if ratio > target_ratio * 1.25:
        painter.fillRect(rect, QColor("#080705"))
        small = QSize(max(1, int(src_size.width() * 0.14)), max(1, int(src_size.height() * 0.14)))
        backdrop = pixmap.scaled(
            small, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        ).scaled(src_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        painter.setOpacity(0.42)
        painter.drawPixmap(
            QPointF(rect.center().x() - backdrop.width() / 2.0, rect.center().y() - backdrop.height() / 2.0),
            backdrop,
        )
        painter.setOpacity(1.0)
        scaled = pixmap.scaled(src_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter.drawPixmap(
            QPointF(rect.center().x() - scaled.width() / 2.0, rect.center().y() - scaled.height() / 2.0),
            scaled,
        )
    else:
        src = pixmap.scaled(src_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        sx = max(0, (src.width() - src_size.width()) // 2)
        sy = max(0, (src.height() - src_size.height()) // 2)
        painter.drawPixmap(rect.topLeft(), src.copy(sx, sy, src_size.width(), src_size.height()))


def _paint_shell_backdrop(painter: QPainter, frame: QRectF, profile: CaseProfile) -> None:
    """Paint the molded plastic or cardboard retail shell behind the artwork."""
    base = QColor(profile.shell_color)
    grad = QLinearGradient(frame.topLeft(), frame.bottomRight())
    if profile.shell_kind in {"translucent_clear", "jewel_clear"}:
        grad.setColorAt(0.0, _mix(base, QColor("#ffffff"), 0.35))
        grad.setColorAt(0.5, base)
        grad.setColorAt(1.0, base.darker(130))
        painter.fillRect(frame, grad)
    elif profile.shell_kind == "translucent_tint":
        grad.setColorAt(0.0, base.lighter(118))
        grad.setColorAt(0.55, base)
        grad.setColorAt(1.0, base.darker(135))
        painter.fillRect(frame, grad)
    elif profile.shell_kind == "cardboard":
        grad.setColorAt(0.0, base.lighter(110))
        grad.setColorAt(1.0, base.darker(125))
        painter.fillRect(frame, grad)
    else:
        grad.setColorAt(0.0, base.lighter(108))
        grad.setColorAt(1.0, base.darker(118))
        painter.fillRect(frame, grad)


def _paint_shell_rim_overlay(
    painter: QPainter, frame: QRectF, inner: QRectF, profile: CaseProfile
) -> None:
    """Paint translucent polycarbonate edge highlights, snap clips, or top lips."""
    radius = profile.radius
    w, h = frame.width(), frame.height()

    if profile.shell_kind in {"translucent_clear", "jewel_clear"}:
        # Crystal-clear molded plastic outer bevel
        rim = QLinearGradient(frame.topLeft(), frame.topRight())
        rim.setColorAt(0.0, QColor(255, 255, 255, 130))
        rim.setColorAt(0.04, QColor(220, 232, 245, 40))
        rim.setColorAt(0.96, QColor(220, 232, 245, 35))
        rim.setColorAt(1.0, QColor(255, 255, 255, 115))
        painter.setPen(QPen(QBrush(rim), max(1.2, w * 0.012)))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(frame.adjusted(0.8, 0.8, -0.8, -0.8), radius, radius)

        # Inner paper insert shadow line
        painter.setPen(QPen(QColor(0, 0, 0, 70), 0.9))
        painter.drawRoundedRect(inner, max(1.0, radius - 2.2), max(1.0, radius - 2.2))

        # Molded side closure tabs (Switch / NDS / PSP style)
        if profile.key in {"switch", "nds", "psp"}:
            tab_h = h * 0.14
            for ty in (frame.top() + h * 0.24, frame.top() + h * 0.64):
                tab = QRectF(frame.right() - w * 0.022, ty, w * 0.022, tab_h)
                painter.fillRect(tab, QColor(255, 255, 255, 75))
    elif profile.shell_kind == "translucent_tint":
        edge = QColor(profile.shell_color).lighter(145)
        edge.setAlpha(155)
        painter.setPen(QPen(edge, max(1.1, w * 0.010)))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(frame.adjusted(0.8, 0.8, -0.8, -0.8), radius, radius)
        painter.setPen(QPen(QColor(0, 0, 0, 80), 0.9))
        painter.drawRoundedRect(inner, max(1.0, radius - 2.2), max(1.0, radius - 2.2))
    elif profile.shell_kind == "keepcase":
        is_light = QColor(profile.shell_color).lightness() > 160
        edge = QColor(255, 255, 255, 165) if is_light else QColor(255, 255, 255, 55)
        painter.setPen(QPen(edge, 1.1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(frame.adjusted(0.7, 0.7, -0.7, -0.7), radius, radius)
    elif profile.shell_kind == "cardboard":
        # Subtle worn matte cardboard crease border
        painter.setPen(QPen(QColor(255, 255, 255, 36), 0.9))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(frame.adjusted(0.8, 0.8, -0.8, -0.8), radius, radius)

    if profile.shell_kind in {"translucent_clear", "translucent_tint", "jewel_clear", "keepcase"}:
        # Subtle physical acrylic/polycarbonate sleeve reflection across the case face
        sheen = QLinearGradient(frame.topLeft(), QPointF(frame.left() + w * 0.62, frame.top() + h * 0.58))
        sheen.setColorAt(0.0, QColor(255, 255, 255, 26))
        sheen.setColorAt(0.45, QColor(255, 255, 255, 10))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(sheen))
        painter.drawRoundedRect(frame, radius, radius)


def _draw_joycon_emblem(painter: QPainter, rect: QRectF, fg: QColor, bg: Optional[QColor] = None) -> None:
    """Draw the iconic asymmetrical Nintendo Switch dual Joy-Con glyph."""
    painter.save()
    if bg is not None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, rect.width() * 0.20, rect.height() * 0.20)
        pad = rect.width() * 0.16
        glyph = rect.adjusted(pad, pad, -pad, -pad)
    else:
        glyph = rect

    gx, gy, gw, gh = glyph.x(), glyph.y(), glyph.width(), glyph.height()
    # Left solid Joy-Con outline + dot
    left = QRectF(gx, gy, gw * 0.44, gh)
    painter.setPen(QPen(fg, max(1.1, gw * 0.11)))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(left, gw * 0.16, gw * 0.16)
    painter.setPen(Qt.NoPen)
    painter.setBrush(fg)
    r_dot = gw * 0.085
    painter.drawEllipse(QPointF(left.center().x(), gy + gh * 0.31), r_dot, r_dot)

    # Right filled Joy-Con + cutout dot
    right = QRectF(gx + gw * 0.56, gy, gw * 0.44, gh)
    right_path = QPainterPath()
    right_path.addRoundedRect(right, gw * 0.16, gw * 0.16)
    dot_path = QPainterPath()
    dot_path.addEllipse(QPointF(right.center().x(), gy + gh * 0.57), r_dot * 1.1, r_dot * 1.1)
    painter.drawPath(right_path.subtracted(dot_path))
    painter.restore()


def _draw_ps_family_logo(painter: QPainter, rect: QRectF, mono: Optional[QColor] = None) -> None:
    """Draw the classic geometric PlayStation 'PS' emblem."""
    painter.save()
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    p_col = mono or QColor("#e11d48")
    s_top = mono or QColor("#f59e0b")
    s_mid = mono or QColor("#10b981")
    s_bot = mono or QColor("#2563eb")

    # Vertical P stem & top loop
    painter.setPen(Qt.NoPen)
    painter.setBrush(p_col)
    stem = QRectF(x + w * 0.34, y + h * 0.04, w * 0.22, h * 0.88)
    painter.drawRoundedRect(stem, 1.0, 1.0)
    loop = QPainterPath()
    loop.moveTo(x + w * 0.54, y + h * 0.06)
    loop.cubicTo(x + w * 0.92, y + h * 0.14, x + w * 0.92, y + h * 0.56, x + w * 0.54, y + h * 0.58)
    loop.lineTo(x + w * 0.54, y + h * 0.06)
    painter.drawPath(loop)

    # Flat angled S floor perspective
    painter.setBrush(s_bot)
    s1 = QPainterPath()
    s1.moveTo(x + w * 0.05, y + h * 0.78)
    s1.lineTo(x + w * 0.42, y + h * 0.64)
    s1.lineTo(x + w * 0.42, y + h * 0.82)
    s1.lineTo(x + w * 0.14, y + h * 0.94)
    s1.closeSubpath()
    painter.drawPath(s1)

    painter.setBrush(s_mid)
    s2 = QPainterPath()
    s2.moveTo(x + w * 0.52, y + h * 0.72)
    s2.lineTo(x + w * 0.94, y + h * 0.58)
    s2.lineTo(x + w * 0.94, y + h * 0.74)
    s2.lineTo(x + w * 0.52, y + h * 0.88)
    s2.closeSubpath()
    painter.drawPath(s2)

    painter.setBrush(s_top)
    painter.drawRect(QRectF(x + w * 0.54, y + h * 0.62, w * 0.36, h * 0.11))
    painter.restore()


def _draw_pal_badge(painter: QPainter, rect: QRectF, fg: QColor, bg: Optional[QColor] = None) -> None:
    painter.save()
    if bg is not None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 1.5, 1.5)
    font = QFont(SANS_FONT)
    font.setPixelSize(max(6, int(rect.height() * 0.72)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(fg)
    painter.drawText(rect, Qt.AlignCenter, "PAL")
    painter.restore()


def _draw_dreamcast_swirl(painter: QPainter, center: QPointF, radius: float, color: QColor) -> None:
    """Draw the European PAL blue Dreamcast spiral."""
    painter.save()
    painter.setBrush(Qt.NoBrush)
    pen = QPen(color, max(1.2, radius * 0.21), Qt.SolidLine, Qt.RoundCap)
    painter.setPen(pen)
    path = QPainterPath()
    steps = 44
    for idx in range(steps + 1):
        t = idx / steps
        angle = t * math.pi * 3.85 - math.pi * 0.35
        r = radius * (0.14 + 0.84 * t)
        pt = QPointF(center.x() + math.cos(angle) * r, center.y() + math.sin(angle) * r)
        if idx == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    painter.drawPath(path)
    painter.restore()


def _draw_xbox_sphere(painter: QPainter, center: QPointF, r: float) -> None:
    painter.save()
    orb = QRadialGradient(center.x() - r * 0.25, center.y() - r * 0.25, r * 1.2)
    orb.setColorAt(0.0, QColor("#f8fafc"))
    orb.setColorAt(0.55, QColor("#cbd5e1"))
    orb.setColorAt(1.0, QColor("#64748b"))
    painter.setPen(QPen(QColor("#94a3b8"), 0.8))
    painter.setBrush(QBrush(orb))
    painter.drawEllipse(center, r, r)

    # Diagonal X arms
    clip = QPainterPath()
    clip.addEllipse(center, r * 0.94, r * 0.94)
    painter.setClipPath(clip)
    pen = QPen(QColor("#65b91a"), max(1.6, r * 0.28), Qt.SolidLine, Qt.RoundCap)
    painter.setPen(pen)
    arm1 = QPainterPath()
    arm1.moveTo(center.x() - r * 0.72, center.y() - r * 0.72)
    arm1.quadTo(center.x(), center.y() - r * 0.15, center.x() + r * 0.72, center.y() + r * 0.72)
    arm2 = QPainterPath()
    arm2.moveTo(center.x() + r * 0.72, center.y() - r * 0.72)
    arm2.quadTo(center.x(), center.y() - r * 0.15, center.x() - r * 0.72, center.y() + r * 0.72)
    painter.drawPath(arm1)
    painter.drawPath(arm2)
    painter.restore()


def _draw_gamecube_cube(painter: QPainter, center: QPointF, r: float) -> None:
    painter.save()
    painter.setPen(QPen(QColor("#e9e6ff"), max(0.8, r * 0.08)))
    # Top face
    top = QPainterPath()
    top.moveTo(center.x(), center.y() - r)
    top.lineTo(center.x() + r * 0.86, center.y() - r * 0.5)
    top.lineTo(center.x(), center.y())
    top.lineTo(center.x() - r * 0.86, center.y() - r * 0.5)
    top.closeSubpath()
    painter.setBrush(QColor("#8e82ee"))
    painter.drawPath(top)

    # Left face
    left = QPainterPath()
    left.moveTo(center.x() - r * 0.86, center.y() - r * 0.5)
    left.lineTo(center.x(), center.y())
    left.lineTo(center.x(), center.y() + r)
    left.lineTo(center.x() - r * 0.86, center.y() + r * 0.5)
    left.closeSubpath()
    painter.setBrush(QColor("#6757d6"))
    painter.drawPath(left)

    # Right face
    right = QPainterPath()
    right.moveTo(center.x() + r * 0.86, center.y() - r * 0.5)
    right.lineTo(center.x(), center.y())
    right.lineTo(center.x(), center.y() + r)
    right.lineTo(center.x() + r * 0.86, center.y() + r * 0.5)
    right.closeSubpath()
    painter.setBrush(QColor("#4334a8"))
    painter.drawPath(right)

    # Inner dark cube core
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#14151c"))
    painter.drawEllipse(center, r * 0.34, r * 0.34)
    painter.restore()


_SWITCH2_STRIP_PIXMAP: Optional[QPixmap] = None


def _switch2_strip_pixmap() -> QPixmap:
    global _SWITCH2_STRIP_PIXMAP
    if _SWITCH2_STRIP_PIXMAP is None:
        path = assets_dir() / "switch2_strip_logo.png"
        _SWITCH2_STRIP_PIXMAP = QPixmap(str(path)) if path.is_file() else QPixmap()
    return _SWITCH2_STRIP_PIXMAP


def _paint_switch2(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    bar = QRectF(inner.left(), inner.top(), inner.width(), inner.height() * 0.145)
    painter.fillRect(bar, QColor("#e60012"))

    logo = _switch2_strip_pixmap()
    if not logo.isNull():
        pad_y = max(2.0, bar.height() * 0.10)
        avail_w = max(8.0, bar.width() * 0.86)
        avail_h = max(6.0, bar.height() - 2.0 * pad_y)
        aspect = logo.width() / max(1, logo.height())
        if avail_w / avail_h > aspect:
            draw_h = avail_h
            draw_w = draw_h * aspect
        else:
            draw_w = avail_w
            draw_h = draw_w / aspect
        target = QRectF(
            bar.center().x() - draw_w / 2.0,
            bar.center().y() - draw_h / 2.0,
            draw_w,
            draw_h,
        )
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(target, logo, QRectF(logo.rect()))
        painter.restore()
        return

    # Fallback centered [Joy-Con emblem] + "2" on top, "NINTENDO SWITCH" stacked underneath
    top_h = bar.height() * 0.50
    icon_s = top_h * 0.82
    font_two = QFont(NINTENDO_FONT)
    font_two.setPixelSize(max(10, int(top_h * 0.92)))
    font_two.setBold(True)
    fm_two = QFontMetrics(font_two)
    two_w = fm_two.horizontalAdvance("2")
    gap = icon_s * 0.22
    group_w = icon_s + gap + two_w
    gx = bar.center().x() - group_w / 2.0
    gy = bar.top() + bar.height() * 0.12

    _draw_joycon_emblem(painter, QRectF(gx, gy, icon_s, icon_s), QColor("#ffffff"))
    painter.setFont(font_two)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(
        QRectF(gx + icon_s + gap, gy - top_h * 0.08, two_w + 4.0, top_h * 1.05),
        Qt.AlignLeft | Qt.AlignVCenter,
        "2",
    )

    sub_font = QFont(NINTENDO_FONT)
    sub_font.setPixelSize(max(6, int(bar.height() * 0.15)))
    sub_font.setBold(True)
    sub_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
    painter.setFont(sub_font)
    painter.drawText(
        QRectF(bar.left(), bar.top() + bar.height() * 0.59, bar.width(), bar.height() * 0.17),
        Qt.AlignCenter,
        "NINTENDO",
    )

    sw_font = QFont(NINTENDO_FONT)
    sw_font.setPixelSize(max(7, int(bar.height() * 0.21)))
    sw_font.setBold(True)
    sw_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.1)
    painter.setFont(sw_font)
    painter.drawText(
        QRectF(bar.left(), bar.top() + bar.height() * 0.74, bar.width(), bar.height() * 0.23),
        Qt.AlignCenter,
        "SWITCH",
    )


def _paint_switch(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    size = min(inner.width() * 0.23, inner.height() * 0.165)
    margin = inner.width() * 0.032
    badge = QRectF(inner.left() + margin, inner.top() + margin * 0.85, size, size)
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#e60012"))
    painter.drawRoundedRect(badge, size * 0.06, size * 0.06)
    icon_box = badge.adjusted(size * 0.22, size * 0.12, -size * 0.22, -size * 0.42)
    _draw_joycon_emblem(painter, icon_box, QColor("#ffffff"))

    nin_font = QFont(NINTENDO_FONT)
    nin_font.setPixelSize(max(4, int(size * 0.12)))
    nin_font.setBold(True)
    nin_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
    painter.setFont(nin_font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(
        QRectF(badge.left(), badge.bottom() - size * 0.37, badge.width(), size * 0.14),
        Qt.AlignCenter,
        "NINTENDO",
    )

    sw_font = QFont(NINTENDO_FONT)
    sw_font.setPixelSize(max(5, int(size * 0.17)))
    sw_font.setBold(True)
    sw_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.7)
    painter.setFont(sw_font)
    painter.drawText(
        QRectF(badge.left(), badge.bottom() - size * 0.24, badge.width(), size * 0.20),
        Qt.AlignCenter,
        "SWITCH",
    )
    painter.restore()


_3DS_STRIP_PIXMAP: Optional[QPixmap] = None


def _3ds_strip_pixmap() -> QPixmap:
    global _3DS_STRIP_PIXMAP
    if _3DS_STRIP_PIXMAP is None:
        path = assets_dir() / "3ds_strip_logo.png"
        _3DS_STRIP_PIXMAP = QPixmap(str(path)) if path.is_file() else QPixmap()
    return _3DS_STRIP_PIXMAP


def _paint_3ds(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    strip_w = inner.width() * 0.145
    strip = QRectF(inner.right() - strip_w, inner.top(), strip_w, inner.height())
    grad = QLinearGradient(strip.topLeft(), strip.topRight())
    grad.setColorAt(0.0, QColor("#e8ecf2"))
    grad.setColorAt(0.16, QColor("#ffffff"))
    grad.setColorAt(1.0, QColor("#f4f6f9"))
    painter.fillRect(strip, grad)

    # Clean vertical divider rule (authentic white PAL 3DS side bar)
    painter.fillRect(QRectF(strip.left(), strip.top(), 1.1, strip.height()), QColor("#d1d5db"))

    logo = _3ds_strip_pixmap()
    if not logo.isNull():
        pad_x = max(1.5, strip_w * 0.14)
        pad_y = max(4.0, strip.height() * 0.08)
        avail_w = max(4.0, strip.width() - 2.0 * pad_x)
        avail_h = max(8.0, strip.height() - 2.0 * pad_y)
        aspect = logo.width() / max(1, logo.height())
        if avail_w / avail_h > aspect:
            draw_h = avail_h
            draw_w = draw_h * aspect
        else:
            draw_w = avail_w
            draw_h = draw_w / aspect
        target = QRectF(
            strip.center().x() - draw_w / 2.0,
            strip.center().y() - draw_h / 2.0,
            draw_w,
            draw_h,
        )
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(target, logo, QRectF(logo.rect()))
        painter.restore()
        return

    # Fallback vertical rotated "NINTENDO 3DS" text if asset is missing
    painter.save()
    cx = strip.center().x()
    cy = strip.center().y()
    painter.translate(cx, cy)
    painter.rotate(-90)
    font = QFont(NINTENDO_FONT)
    font.setPixelSize(max(7, int(strip_w * 0.44)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
    painter.setFont(font)
    fm = QFontMetrics(font)
    nint = "NINTENDO "
    mid = "3D"
    tail = "S"
    w_nint = fm.horizontalAdvance(nint)
    w_mid = fm.horizontalAdvance(mid)
    w_tail = fm.horizontalAdvance(tail)
    total_w = w_nint + w_mid + w_tail
    start_x = -total_w / 2.0
    h_box = strip_w * 0.9
    painter.setPen(QColor("#17191c"))
    painter.drawText(QRectF(start_x, -h_box / 2.0, w_nint + w_mid + 2.0, h_box), Qt.AlignVCenter | Qt.AlignLeft, nint + mid)
    painter.setPen(QColor("#d32f2f"))
    painter.drawText(QRectF(start_x + w_nint + w_mid, -h_box / 2.0, w_tail + 2.0, h_box), Qt.AlignVCenter | Qt.AlignLeft, tail)
    painter.restore()


def _paint_nds(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    strip_w = inner.width() * 0.135
    strip = QRectF(inner.left(), inner.top(), strip_w, inner.height())
    grad = QLinearGradient(strip.topLeft(), strip.topRight())
    grad.setColorAt(0.0, QColor("#e5e8ed"))
    grad.setColorAt(0.82, QColor("#ffffff"))
    grad.setColorAt(1.0, QColor("#cfd5de"))
    painter.fillRect(strip, grad)
    painter.fillRect(QRectF(strip.right() - 1.3, strip.top(), 1.3, strip.height()), QColor("#94a3b8"))

    # Twin-screen DS emblem at top of strip
    pad = strip_w * 0.22
    ds_top = QRectF(strip.left() + pad, strip.top() + strip.height() * 0.05, strip_w - pad * 2, strip_w * 0.36)
    ds_bot = QRectF(strip.left() + pad, ds_top.bottom() + 2.0, strip_w - pad * 2, strip_w * 0.36)
    painter.setPen(QPen(QColor("#334155"), 1.0))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(ds_top)
    painter.drawRect(ds_bot)

    painter.save()
    painter.translate(strip.center().x(), strip.center().y() + strip.height() * 0.06)
    painter.rotate(-90)
    font = QFont(NINTENDO_FONT)
    font.setPixelSize(max(7, int(strip_w * 0.42)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
    painter.setFont(font)
    painter.setPen(QColor("#1e293b"))
    label_rect = QRectF(-strip.height() * 0.36, -strip_w * 0.45, strip.height() * 0.72, strip_w * 0.9)
    painter.drawText(label_rect, Qt.AlignCenter, "NINTENDO DS")
    painter.restore()


def _paint_wii(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    bar_h = inner.height() * 0.125
    bar = QRectF(inner.left(), inner.top(), inner.width(), bar_h)
    grad = QLinearGradient(bar.topLeft(), bar.bottomLeft())
    grad.setColorAt(0.0, QColor("#ffffff"))
    grad.setColorAt(1.0, QColor("#e8edf3"))
    painter.fillRect(bar, grad)

    # Signature silver curved underline arc
    curve = QPainterPath()
    curve.moveTo(bar.left(), bar.bottom())
    curve.quadTo(bar.center().x(), bar.bottom() - bar_h * 0.28, bar.right(), bar.bottom() - bar_h * 0.08)
    painter.setPen(QPen(QColor("#b8c2ce"), 1.6))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(curve)

    font = QFont(NINTENDO_FONT)
    font.setPixelSize(max(9, int(bar_h * 0.56)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#7b8594"))
    painter.drawText(QRectF(bar.left() + bar_h * 0.45, bar.top(), bar.width() * 0.5, bar_h * 0.9), Qt.AlignLeft | Qt.AlignVCenter, "Wii")

    _draw_pal_badge(
        painter,
        QRectF(bar.right() - bar_h * 1.15, bar.top() + bar_h * 0.26, bar_h * 0.85, bar_h * 0.42),
        QColor("#64748b"),
        QColor("#e2e8f0"),
    )


def _paint_wiiu(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    bar_h = inner.height() * 0.125
    bar = QRectF(inner.left(), inner.top(), inner.width(), bar_h)
    grad = QLinearGradient(bar.topLeft(), bar.bottomLeft())
    grad.setColorAt(0.0, QColor("#00a8dc"))
    grad.setColorAt(1.0, QColor("#0082ad"))
    painter.fillRect(bar, grad)

    curve = QPainterPath()
    curve.moveTo(bar.left(), bar.bottom() - bar_h * 0.06)
    curve.quadTo(bar.center().x(), bar.bottom() + bar_h * 0.14, bar.right(), bar.bottom() - bar_h * 0.12)
    painter.setPen(QPen(QColor("#ffffff"), 1.6))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(curve)

    font = QFont(NINTENDO_FONT)
    font.setPixelSize(max(9, int(bar_h * 0.54)))
    font.setBold(True)
    painter.setFont(font)
    fm = QFontMetrics(font)
    wii_x = bar.left() + bar_h * 0.45
    wii_w = fm.horizontalAdvance("Wii") + 4.0
    painter.setPen(QColor("#ffffff"))
    painter.drawText(QRectF(wii_x, bar.top(), wii_w, bar_h * 0.88), Qt.AlignLeft | Qt.AlignVCenter, "Wii")

    # Signature white 'U' pill badge positioned dynamically after 'Wii'
    u_box = QRectF(wii_x + wii_w + bar_h * 0.08, bar.top() + bar_h * 0.20, bar_h * 0.54, bar_h * 0.50)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(u_box, bar_h * 0.14, bar_h * 0.14)
    painter.setPen(QColor("#008fc0"))
    painter.drawText(u_box, Qt.AlignCenter, "U")

    _draw_pal_badge(
        painter,
        QRectF(bar.right() - bar_h * 1.15, bar.top() + bar_h * 0.24, bar_h * 0.85, bar_h * 0.42),
        QColor("#007ca3"),
        QColor("#e0f7ff"),
    )


def _paint_gamecube(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    bar_h = inner.height() * 0.15
    bar = QRectF(inner.left(), inner.top(), inner.width(), bar_h)
    painter.fillRect(bar, QColor("#0d0e13"))

    # Purple curved diagonal sash at left + metallic violet line
    sash = QPainterPath()
    sash.moveTo(bar.left(), bar.top())
    sash.lineTo(bar.left() + bar.width() * 0.46, bar.top())
    sash.quadTo(bar.left() + bar.width() * 0.34, bar.bottom(), bar.left(), bar.bottom())
    sash.closeSubpath()
    painter.fillPath(sash, QColor("#4e3fb0"))
    painter.fillRect(QRectF(bar.left(), bar.bottom() - 1.5, bar.width(), 1.5), QColor("#6959cd"))

    cube_r = bar_h * 0.34
    _draw_gamecube_cube(painter, QPointF(bar.left() + bar_h * 0.55, bar.center().y()), cube_r)

    pal_rect = QRectF(bar.right() - bar_h * 0.92, bar.top() + bar_h * 0.28, bar_h * 0.74, bar_h * 0.38)
    text_x = bar.left() + bar_h * 1.05
    avail_w = pal_rect.left() - text_x - 4.0

    micro = QFont(SANS_FONT)
    micro.setPixelSize(max(5, int(bar_h * 0.17)))
    micro.setBold(True)
    micro.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
    painter.setFont(micro)
    painter.setPen(QColor("#cbd5e1"))
    painter.drawText(QRectF(text_x, bar.top() + bar_h * 0.14, avail_w, bar_h * 0.24), Qt.AlignLeft | Qt.AlignVCenter, "NINTENDO")

    font = QFont(SANS_FONT)
    font.setPixelSize(max(6, int(bar_h * 0.34)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    text_rect = QRectF(text_x, bar.top() + bar_h * 0.34, avail_w, bar_h * 0.56)
    shown = QFontMetrics(font).elidedText("GAMECUBE", Qt.ElideRight, int(text_rect.width()))
    painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, shown)
    _draw_pal_badge(
        painter,
        pal_rect,
        QColor("#111318"),
        QColor("#e2e8f0"),
    )


def _paint_ps3(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    # Clear BD header lip above insert already visible from inner offset!
    lip = QRectF(frame.left(), frame.top(), frame.width(), inner.top() - frame.top())
    lip_grad = QLinearGradient(lip.topLeft(), lip.bottomLeft())
    lip_grad.setColorAt(0.0, QColor(255, 255, 255, 115))
    lip_grad.setColorAt(0.5, QColor(200, 212, 228, 60))
    lip_grad.setColorAt(1.0, QColor(140, 155, 175, 95))
    painter.fillRect(lip, lip_grad)

    # Embossed Blu-ray mark inside clear top lip
    bd_font = QFont(SANS_FONT)
    bd_font.setPixelSize(max(5, int(lip.height() * 0.62)))
    bd_font.setBold(True)
    painter.setFont(bd_font)
    painter.setPen(QColor(255, 255, 255, 130))
    painter.drawText(lip, Qt.AlignCenter, "Blu-ray Disc")

    bar_h = inner.height() * 0.12
    bar = QRectF(inner.left(), inner.top(), inner.width(), bar_h)
    grad = QLinearGradient(bar.topLeft(), bar.bottomLeft())
    grad.setColorAt(0.0, QColor("#0c0e14"))
    grad.setColorAt(1.0, QColor("#181c26"))
    painter.fillRect(bar, grad)
    painter.fillRect(QRectF(bar.left(), bar.bottom() - 1.2, bar.width(), 1.2), QColor("#cbd5e1"))

    pad = bar_h * 0.18
    ps_rect = QRectF(bar.left() + pad * 1.5, bar.top() + pad, bar_h * 0.72, bar_h - pad * 2)
    _draw_ps_family_logo(painter, ps_rect, mono=QColor("#f8fafc"))

    font = QFont(SANS_FONT)
    font.setPixelSize(max(8, int(bar_h * 0.56)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 1.4)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(
        QRectF(ps_rect.right() + pad, bar.top(), bar.width() * 0.65, bar_h),
        Qt.AlignLeft | Qt.AlignVCenter,
        "PS3",
    )


def _paint_ps2(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    bar_h = inner.height() * 0.128
    bar = QRectF(inner.left(), inner.top(), inner.width(), bar_h)
    painter.fillRect(bar, QColor("#07080c"))
    painter.fillRect(QRectF(bar.left(), bar.bottom() - 1.5, bar.width(), 1.5), QColor("#2563eb"))

    pad = bar_h * 0.18
    ps_rect = QRectF(bar.left() + pad * 1.4, bar.top() + pad, bar_h * 0.72, bar_h - pad * 2)
    _draw_ps_family_logo(painter, ps_rect)

    pal_rect = QRectF(bar.right() - bar_h * 0.95, bar.top() + bar_h * 0.28, bar_h * 0.75, bar_h * 0.42)
    font = QFont(SANS_FONT)
    font.setPixelSize(max(7, int(bar_h * 0.38)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.4)
    painter.setFont(font)
    painter.setPen(QColor("#f8fafc"))
    text_rect = QRectF(ps_rect.right() + pad, bar.top(), pal_rect.left() - (ps_rect.right() + pad * 1.5), bar_h)
    shown = QFontMetrics(font).elidedText("PlayStation 2", Qt.ElideRight, int(text_rect.width()))
    painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, shown)
    _draw_pal_badge(painter, pal_rect, QColor("#e2e8f0"))


def _paint_ps1(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    # Chunky clear ribbed CD tray hinge on the LEFT edge
    hinge_w = inner.width() * 0.105
    hinge = QRectF(inner.left(), inner.top(), hinge_w, inner.height())
    h_grad = QLinearGradient(hinge.topLeft(), hinge.topRight())
    h_grad.setColorAt(0.0, QColor("#6b7280"))
    h_grad.setColorAt(0.3, QColor("#374151"))
    h_grad.setColorAt(0.75, QColor("#1f2937"))
    h_grad.setColorAt(1.0, QColor("#9ca3af"))
    painter.fillRect(hinge, h_grad)
    # Fine horizontal molded jewel-case teeth ribs
    rib_pen = QPen(QColor(255, 255, 255, 42), 1.0)
    painter.setPen(rib_pen)
    step = max(3.0, inner.height() / 42.0)
    y = hinge.top() + step
    while y < hinge.bottom() - 2.0:
        painter.drawLine(QPointF(hinge.left() + 1.5, y), QPointF(hinge.right() - 1.5, y))
        y += step

    # Iconic European PAL black PlayStation bottom strip
    bar_h = inner.height() * 0.132
    bar = QRectF(hinge.right(), inner.bottom() - bar_h, inner.width() - hinge_w, bar_h)
    painter.fillRect(bar, QColor("#060709"))
    painter.fillRect(QRectF(bar.left(), bar.top(), bar.width(), 1.0), QColor("#cbd5e1"))

    pad = bar_h * 0.18
    ps_rect = QRectF(bar.left() + pad * 1.2, bar.top() + pad, bar_h * 0.72, bar_h - pad * 2)
    _draw_ps_family_logo(painter, ps_rect)

    pal_rect = QRectF(bar.right() - bar_h * 0.95, bar.top() + bar_h * 0.28, bar_h * 0.75, bar_h * 0.42)
    font = QFont(SANS_FONT)
    font.setPixelSize(max(7, int(bar_h * 0.39)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    text_rect = QRectF(ps_rect.right() + pad * 0.9, bar.top(), pal_rect.left() - (ps_rect.right() + pad * 1.4), bar_h)
    shown = QFontMetrics(font).elidedText("PlayStation", Qt.ElideRight, int(text_rect.width()))
    painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, shown)
    _draw_pal_badge(
        painter,
        pal_rect,
        QColor("#060709"),
        QColor("#f1f5f9"),
    )


def _paint_psp(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    bar_h = inner.height() * 0.125
    bar = QRectF(inner.left(), inner.top(), inner.width(), bar_h)
    grad = QLinearGradient(bar.topLeft(), bar.bottomLeft())
    grad.setColorAt(0.0, QColor("#12151d"))
    grad.setColorAt(1.0, QColor("#090b10"))
    painter.fillRect(bar, grad)
    painter.fillRect(QRectF(bar.left(), bar.bottom() - 1.3, bar.width(), 1.3), QColor("#cbd5e1"))

    font = QFont(SANS_FONT)
    font.setPixelSize(max(9, int(bar_h * 0.56)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 2.2)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(QRectF(bar.left() + bar_h * 0.5, bar.top(), bar.width() * 0.65, bar_h), Qt.AlignLeft | Qt.AlignVCenter, "PSP")

    umd = QRectF(bar.right() - bar_h * 1.15, bar.top() + bar_h * 0.28, bar_h * 0.85, bar_h * 0.44)
    painter.setPen(QPen(QColor("#94a3b8"), 1.0))
    painter.setBrush(QColor("#1e293b"))
    painter.drawRoundedRect(umd, 2.0, 2.0)
    u_font = QFont(SANS_FONT)
    u_font.setPixelSize(max(6, int(umd.height() * 0.65)))
    u_font.setBold(True)
    painter.setFont(u_font)
    painter.setPen(QColor("#e2e8f0"))
    painter.drawText(umd, Qt.AlignCenter, "UMD")


def _paint_psvita(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    bar_h = inner.height() * 0.125
    bar = QRectF(inner.left(), inner.top(), inner.width(), bar_h)
    grad = QLinearGradient(bar.topLeft(), bar.bottomLeft())
    grad.setColorAt(0.0, QColor("#0060df"))
    grad.setColorAt(1.0, QColor("#0042a3"))
    painter.fillRect(bar, grad)
    painter.fillRect(QRectF(bar.left(), bar.bottom() - 1.3, bar.width(), 1.3), QColor("#7dd3fc"))

    pad = bar_h * 0.2
    ps_rect = QRectF(bar.left() + pad * 1.4, bar.top() + pad, bar_h * 0.68, bar_h - pad * 2)
    _draw_ps_family_logo(painter, ps_rect, mono=QColor("#ffffff"))

    font = QFont(SANS_FONT)
    font.setPixelSize(max(8, int(bar_h * 0.48)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(QRectF(ps_rect.right() + pad, bar.top(), bar.width() * 0.7, bar_h), Qt.AlignLeft | Qt.AlignVCenter, "PS VITA")


def _paint_xbox360(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    bar_h = inner.height() * 0.132
    bar = QRectF(inner.left(), inner.top(), inner.width(), bar_h)
    grad = QLinearGradient(bar.topLeft(), bar.bottomLeft())
    grad.setColorAt(0.0, QColor("#ffffff"))
    grad.setColorAt(1.0, QColor("#e7ecef"))
    painter.fillRect(bar, grad)

    # Signature lime-green swooping curve on top right + lower edge
    wave = QPainterPath()
    wave.moveTo(bar.left(), bar.bottom())
    wave.quadTo(bar.center().x() * 0.85, bar.bottom() - bar_h * 0.26, bar.right(), bar.bottom() - bar_h * 0.05)
    wave.lineTo(bar.right(), bar.bottom() + bar_h * 0.04)
    wave.lineTo(bar.left(), bar.bottom() + bar_h * 0.04)
    wave.closeSubpath()
    painter.fillPath(wave, QColor("#78c81e"))

    r = bar_h * 0.34
    orb_c = QPointF(bar.left() + bar_h * 0.56, bar.center().y() - bar_h * 0.04)
    _draw_xbox_sphere(painter, orb_c, r)

    font = QFont(SANS_FONT)
    font.setPixelSize(max(7, int(bar_h * 0.44)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.7)
    painter.setFont(font)
    fm = QFontMetrics(font)
    xbox_x = orb_c.x() + r + 5.0
    xbox_w = fm.horizontalAdvance("XBOX") + 5.0
    painter.setPen(QColor("#3c4856"))
    painter.drawText(QRectF(xbox_x, bar.top(), xbox_w, bar_h * 0.88), Qt.AlignLeft | Qt.AlignVCenter, "XBOX")
    painter.setPen(QColor("#5bb416"))
    painter.drawText(QRectF(xbox_x + xbox_w, bar.top(), bar.width() * 0.3, bar_h * 0.88), Qt.AlignLeft | Qt.AlignVCenter, "360")
    _draw_pal_badge(painter, QRectF(bar.right() - bar_h * 0.9, bar.top() + bar_h * 0.2, bar_h * 0.72, bar_h * 0.36), QColor("#475569"))


def _paint_xbox(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    bar_h = inner.height() * 0.132
    bar = QRectF(inner.left(), inner.top(), inner.width(), bar_h)
    grad = QLinearGradient(bar.topLeft(), bar.bottomLeft())
    grad.setColorAt(0.0, QColor("#0d3d0d"))
    grad.setColorAt(1.0, QColor("#185c18"))
    painter.fillRect(bar, grad)
    painter.fillRect(QRectF(bar.left(), bar.bottom() - 2.0, bar.width(), 2.0), QColor("#84cc16"))

    r = bar_h * 0.32
    orb_c = QPointF(bar.left() + bar_h * 0.54, bar.center().y())
    _draw_xbox_sphere(painter, orb_c, r)

    font = QFont(SANS_FONT)
    font.setPixelSize(max(8, int(bar_h * 0.48)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 1.4)
    painter.setFont(font)
    painter.setPen(QColor("#d9f99d"))
    painter.drawText(QRectF(orb_c.x() + r + 6.0, bar.top(), bar.width() * 0.65, bar_h), Qt.AlignLeft | Qt.AlignVCenter, "XBOX")
    _draw_pal_badge(painter, QRectF(bar.right() - bar_h * 0.9, bar.top() + bar_h * 0.25, bar_h * 0.72, bar_h * 0.38), QColor("#ecfccb"))


def _paint_dreamcast(painter: QPainter, frame: QRectF, inner: QRectF, _profile: CaseProfile) -> None:
    # Chunky clear-blue ribbed PAL spine tray on LEFT
    hinge_w = inner.width() * 0.095
    hinge = QRectF(inner.left(), inner.top(), hinge_w, inner.height())
    h_grad = QLinearGradient(hinge.topLeft(), hinge.topRight())
    h_grad.setColorAt(0.0, QColor("#3b82f6"))
    h_grad.setColorAt(0.5, QColor("#1d4ed8"))
    h_grad.setColorAt(1.0, QColor("#93c5fd"))
    painter.fillRect(hinge, h_grad)
    painter.setPen(QPen(QColor(255, 255, 255, 65), 1.0))
    step = max(3.5, inner.height() / 36.0)
    y = hinge.top() + step
    while y < hinge.bottom() - 2.0:
        painter.drawLine(QPointF(hinge.left() + 1.5, y), QPointF(hinge.right() - 1.5, y))
        y += step

    # European PAL Dreamcast white+blue top band with PAL blue spiral
    bar_h = inner.height() * 0.148
    bar = QRectF(hinge.right(), inner.top(), inner.width() - hinge_w, bar_h)
    painter.fillRect(bar, QColor("#0050b8"))
    white_tab = QRectF(bar.right() - bar_h * 1.1, bar.top(), bar_h * 1.1, bar_h)
    painter.fillRect(white_tab, QColor("#ffffff"))

    _draw_dreamcast_swirl(painter, white_tab.center(), bar_h * 0.34, QColor("#0050b8"))

    font = QFont(SANS_FONT)
    font.setPixelSize(max(8, int(bar_h * 0.44)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(
        QRectF(bar.left() + bar_h * 0.45, bar.top(), bar.width() - white_tab.width() - bar_h * 0.5, bar_h),
        Qt.AlignLeft | Qt.AlignVCenter,
        "Dreamcast",
    )


def _paint_n64_or_snes(painter: QPainter, frame: QRectF, inner: QRectF, profile: CaseProfile) -> None:
    # Classic European PAL landscape black cardboard box frame already sets outer matte black;
    # paint the authentic top header strip inside `inner`.
    bar_h = inner.height() * 0.13
    bar = QRectF(inner.left(), inner.top(), inner.width(), bar_h)
    painter.fillRect(bar, QColor("#0e1014"))

    if profile.key == "n64":
        # Classic red/blue/green/yellow N64 corner block mark
        r = bar_h * 0.34
        cx, cy = bar.left() + bar_h * 0.65, bar.center().y()
        for idx, col in enumerate(("#e11d48", "#2563eb", "#16a34a", "#eab308")):
            painter.fillRect(
                QRectF(cx - r + (idx % 2) * r, cy - r + (idx // 2) * r, r * 0.9, r * 0.9),
                QColor(col),
            )
        label = "NINTENDO 64"
        accent = "#e11d48"
    else:
        # Classic 4-dot PAL Super Nintendo button swirl
        cx, cy = bar.left() + bar_h * 0.65, bar.center().y()
        dot = bar_h * 0.14
        for dx, dy, col in (
            (-dot * 1.1, 0, "#dc2626"),
            (dot * 1.1, 0, "#eab308"),
            (0, -dot * 1.1, "#2563eb"),
            (0, dot * 1.1, "#16a34a"),
        ):
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(col))
            painter.drawEllipse(QPointF(cx + dx, cy + dy), dot * 0.72, dot * 0.72)
        label = "SUPER NINTENDO"
        accent = "#94a3b8"

    font = QFont(SANS_FONT)
    font.setPixelSize(max(7, int(bar_h * 0.42)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.9)
    painter.setFont(font)
    painter.setPen(QColor("#f8fafc"))
    painter.drawText(QRectF(bar.left() + bar_h * 1.35, bar.top(), bar.width() * 0.7, bar_h), Qt.AlignLeft | Qt.AlignVCenter, label)
    painter.fillRect(QRectF(bar.left(), bar.bottom() - 1.5, bar.width(), 1.5), QColor(accent))


def _paint_gameboy_family(painter: QPainter, frame: QRectF, inner: QRectF, profile: CaseProfile) -> None:
    strip_w = inner.width() * 0.145
    strip = QRectF(inner.left(), inner.top(), strip_w, inner.height())
    if profile.key == "gba":
        grad = QLinearGradient(strip.topLeft(), strip.bottomLeft())
        grad.setColorAt(0.0, QColor("#5b3cc4"))
        grad.setColorAt(1.0, QColor("#3a2284"))
        painter.fillRect(strip, grad)
        ink = QColor("#ffffff")
    elif profile.key == "gbc":
        grad = QLinearGradient(strip.topLeft(), strip.bottomLeft())
        grad.setColorAt(0.0, QColor("#9333ea"))
        grad.setColorAt(0.5, QColor("#3b82f6"))
        grad.setColorAt(1.0, QColor("#10b981"))
        painter.fillRect(strip, grad)
        ink = QColor("#ffffff")
    else:
        painter.fillRect(strip, QColor("#cfd4dc"))
        ink = QColor("#1e2968")

    painter.save()
    painter.translate(strip.center().x(), strip.center().y())
    painter.rotate(-90)
    font = QFont(SANS_FONT)
    font.setPixelSize(max(6, int(strip_w * 0.36)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
    painter.setFont(font)
    painter.setPen(ink)
    painter.drawText(
        QRectF(-strip.height() * 0.45, -strip_w * 0.45, strip.height() * 0.9, strip_w * 0.9),
        Qt.AlignCenter,
        profile.band_label,
    )
    painter.restore()


def _paint_sega_or_retro(painter: QPainter, frame: QRectF, inner: QRectF, profile: CaseProfile) -> None:
    bar_h = inner.height() * 0.13
    bar = QRectF(inner.left(), inner.top(), inner.width(), bar_h)
    bg = QColor(profile.header_bg)
    accent = QColor(profile.header_accent)
    ink = QColor(profile.header_text)

    if profile.key == "mastersystem":
        # White Master System PAL grid background on top bar
        painter.fillRect(bar, bg)
        painter.setPen(QPen(QColor("#cbd5e1"), 0.8))
        step = max(6.0, bar.width() / 12.0)
        x = bar.left() + step
        while x < bar.right():
            painter.drawLine(QPointF(x, bar.top()), QPointF(x, bar.bottom()))
            x += step
        painter.fillRect(QRectF(bar.left(), bar.bottom() - 2.0, bar.width(), 2.0), QColor("#dc2626"))
    else:
        grad = QLinearGradient(bar.topLeft(), bar.bottomLeft())
        grad.setColorAt(0.0, _mix(bg, accent, 0.14))
        grad.setColorAt(1.0, bg.darker(120))
        painter.fillRect(bar, grad)
        painter.fillRect(QRectF(bar.left(), bar.bottom() - 1.5, bar.width(), 1.5), accent)

    font = QFont(SANS_FONT)
    font.setPixelSize(max(7, int(bar_h * 0.44)))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
    painter.setFont(font)
    painter.setPen(ink)
    painter.drawText(
        QRectF(bar.left() + bar_h * 0.45, bar.top(), bar.width() - bar_h * 0.9, bar_h),
        Qt.AlignCenter,
        profile.band_label,
    )


_OVERLAY_PAINTERS: dict[str, Callable[[QPainter, QRectF, QRectF, CaseProfile], None]] = {
    "switch2": _paint_switch2,
    "switch": _paint_switch,
    "3ds": _paint_3ds,
    "nds": _paint_nds,
    "wii": _paint_wii,
    "wiiu": _paint_wiiu,
    "gamecube": _paint_gamecube,
    "ps3": _paint_ps3,
    "ps2": _paint_ps2,
    "ps1": _paint_ps1,
    "psp": _paint_psp,
    "psvita": _paint_psvita,
    "xbox360": _paint_xbox360,
    "xbox": _paint_xbox,
    "dreamcast": _paint_dreamcast,
    "n64": _paint_n64_or_snes,
    "snes": _paint_n64_or_snes,
    "gb": _paint_gameboy_family,
    "gbc": _paint_gameboy_family,
    "gba": _paint_gameboy_family,
}


_OVERLAY_CACHE: dict[str, Optional[tuple[QPixmap, QRectF]]] = {}
_SPINE_CACHE: dict[str, Optional[QPixmap]] = {}


def _detect_transparent_window(pixmap: QPixmap) -> QRectF:
    """Find the normalized [0..1] bounding box of the interior transparent cutout in a PNG overlay."""
    size = 128
    probe = pixmap.toImage().scaled(size, size, Qt.IgnoreAspectRatio, Qt.FastTransformation)
    cx, cy = size // 2, size // 2
    if probe.pixelColor(cx, cy).alpha() >= 64:
        best_dist = 10**9
        found = False
        for y in range(12, size - 12):
            for x in range(12, size - 12):
                if probe.pixelColor(x, y).alpha() < 64:
                    d = (x - cx) ** 2 + (y - cy) ** 2
                    if d < best_dist:
                        best_dist = d
                        cx, cy = x, y
                        found = True
        if not found:
            return QRectF(0.0, 0.0, 1.0, 1.0)

    visited = {(cx, cy)}
    q = deque([(cx, cy)])
    min_x, min_y = cx, cy
    max_x, max_y = cx, cy
    while q:
        px, py = q.popleft()
        if px < min_x:
            min_x = px
        if py < min_y:
            min_y = py
        if px > max_x:
            max_x = px
        if py > max_y:
            max_y = py
        for nx, ny in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
            if 2 <= nx < size - 2 and 2 <= ny < size - 2 and (nx, ny) not in visited:
                if probe.pixelColor(nx, ny).alpha() < 64:
                    visited.add((nx, ny))
                    q.append((nx, ny))

    pad = 1.0 / size
    x0 = max(0.0, min_x / size - pad)
    y0 = max(0.0, min_y / size - pad)
    x1 = min(1.0, (max_x + 1) / size + pad)
    y1 = min(1.0, (max_y + 1) / size + pad)
    return QRectF(x0, y0, max(0.05, x1 - x0), max(0.05, y1 - y0))


def load_spine_texture(system_key: str, side: str = "left") -> Optional[QPixmap]:
    """Load an authentic vertical spine (left) or clasp (right) PNG texture if available."""
    key = (system_key or "").strip().lower()
    if not key:
        return None
    suffix = "_right.png" if side == "right" else "_spine.png"
    from ..paths import data_dir

    candidates = (
        data_dir() / "cases" / f"{key}{suffix}",
        assets_dir() / "cases" / f"{key}{suffix}",
    )
    for path in candidates:
        if not path.is_file():
            continue
        cache_key = f"{key}{suffix}:{path}:{path.stat().st_mtime_ns}"
        if cache_key in _SPINE_CACHE:
            return _SPINE_CACHE[cache_key]
        pix = QPixmap(str(path))
        if pix.isNull():
            _SPINE_CACHE[cache_key] = None
            continue
        _SPINE_CACHE[cache_key] = pix
        return pix
    return None


def load_case_overlay(system_key: str) -> Optional[tuple[QPixmap, QRectF]]:
    """Load an authentic PNG case overlay template from user data or bundled assets if available."""
    key = (system_key or "").strip().lower()
    if not key:
        return None
    from ..paths import data_dir

    candidates = (
        data_dir() / "cases" / f"{key}.png",
        assets_dir() / "cases" / f"{key}.png",
    )
    for path in candidates:
        if not path.is_file():
            continue
        cache_key = f"{key}:{path}:{path.stat().st_mtime_ns}"
        if cache_key in _OVERLAY_CACHE:
            return _OVERLAY_CACHE[cache_key]
        pix = QPixmap(str(path))
        if pix.isNull():
            _OVERLAY_CACHE[cache_key] = None
            continue
        result = (pix, _detect_transparent_window(pix))
        _OVERLAY_CACHE[cache_key] = result
        return result
    return None


def paint_console_case(
    painter: QPainter,
    frame: QRectF,
    profile: CaseProfile,
    pixmap: Optional[QPixmap],
    placeholder_fn: Callable[[QPainter, QRectF], None],
) -> QRectF:
    """Render an authentic physical retail console case and return its artwork rect."""
    template = load_case_overlay(profile.key)
    if template is not None:
        overlay_pix, norm_win = template
        art = QRectF(
            frame.left() + frame.width() * norm_win.x(),
            frame.top() + frame.height() * norm_win.y(),
            max(8.0, frame.width() * norm_win.width()),
            max(8.0, frame.height() * norm_win.height()),
        )
        painter.save()
        # Keep cover artwork safely inside the outer translucent plastic case rim
        clip_path = QPainterPath()
        clip_rect = frame.adjusted(
            frame.width() * 0.015,
            frame.height() * 0.012,
            -frame.width() * 0.015,
            -frame.height() * 0.012,
        )
        clip_path.addRoundedRect(clip_rect, max(2.0, profile.radius * 0.8), max(2.0, profile.radius * 0.8))
        painter.setClipPath(clip_path)
        if pixmap is not None and not pixmap.isNull():
            _draw_cover_art(painter, art, pixmap)
        else:
            placeholder_fn(painter, art)
        painter.restore()
        painter.drawPixmap(frame.toRect(), overlay_pix)
        return art

    w, h = frame.width(), frame.height()
    bl, bt, br, bb = profile.bezel
    inner = QRectF(
        frame.left() + w * bl,
        frame.top() + h * bt,
        max(16.0, w * (1.0 - bl - br)),
        max(16.0, h * (1.0 - bt - bb)),
    )
    art = console_art_rect(frame, profile)

    _paint_shell_backdrop(painter, frame, profile)

    painter.save()
    art_clip = QPainterPath()
    art_clip.addRoundedRect(art, max(1.0, profile.radius * 0.35), max(1.0, profile.radius * 0.35))
    painter.setClipPath(art_clip)
    if pixmap is not None and not pixmap.isNull():
        _draw_cover_art(painter, art, pixmap)
    else:
        placeholder_fn(painter, art)
    painter.restore()

    overlay = _OVERLAY_PAINTERS.get(profile.key, _paint_sega_or_retro)
    painter.save()
    inner_clip = QPainterPath()
    inner_clip.addRoundedRect(inner, max(1.0, profile.radius * 0.45), max(1.0, profile.radius * 0.45))
    painter.setClipPath(inner_clip)
    overlay(painter, frame, inner, profile)
    painter.restore()

    _paint_shell_rim_overlay(painter, frame, inner, profile)
    return art


def paint_console_spine(
    painter: QPainter, target: QRectF, profile: CaseProfile, turn: float
) -> None:
    """Paint the 3D side spine matching real polycarbonate / jewel / cardboard physics."""
    width = target.width()
    max_depth = 26.0 * (width / 222.0) * 0.55 * profile.depth_scale
    base = QColor(profile.spine_color)
    clamped = max(-1.0, min(1.0, float(turn)))

    left_depth = max_depth * (0.28 + 0.72 * max(0.0, clamped))
    right_depth = max_depth * (0.28 + 0.72 * max(0.0, -clamped))

    for is_left, depth in ((True, left_depth), (False, right_depth)):
        spine_tex = load_spine_texture(profile.key, "left" if is_left else "right")
        path = QPainterPath()
        if is_left:
            x0, x1 = target.left(), target.left() - depth
        else:
            x0, x1 = target.right(), target.right() + depth
        p0 = QPointF(x0, target.top())
        p1 = QPointF(x1, target.top() + depth * 0.32)
        p2 = QPointF(x1, target.bottom() - depth * 0.32)
        p3 = QPointF(x0, target.bottom())
        path.moveTo(p0)
        path.lineTo(p1)
        path.lineTo(p2)
        path.lineTo(p3)
        path.closeSubpath()

        if spine_tex is not None and not spine_tex.isNull() and depth > 1.5:
            painter.save()
            painter.setClipPath(path)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            src_poly = QPolygonF(QRectF(spine_tex.rect()))
            if is_left:
                dst_poly = QPolygonF([p1, p0, p3, p2])
            else:
                dst_poly = QPolygonF([p0, p1, p2, p3])
            tx = QTransform()
            if QTransform.quadToQuad(src_poly, dst_poly, tx):
                painter.setTransform(tx, True)
                painter.drawPixmap(spine_tex.rect(), spine_tex)
            painter.restore()
            shade = QLinearGradient(x0, 0, x1, 0)
            shade.setColorAt(0.0, QColor(0, 0, 0, 12))
            shade.setColorAt(1.0, QColor(0, 0, 0, 72))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(shade))
            painter.drawPath(path)
            continue

        grad = QLinearGradient(x0, 0, x1, 0)
        if profile.shell_kind in {"translucent_clear", "jewel_clear"}:
            # Translucent outer acrylic showing crisp inner printed insert hue
            grad.setColorAt(0.0, _mix(base, QColor("#ffffff"), 0.25))
            grad.setColorAt(0.28, base)
            grad.setColorAt(0.75, base.darker(135))
            grad.setColorAt(1.0, base.darker(195))
        elif profile.shell_kind == "translucent_tint":
            grad.setColorAt(0.0, base.lighter(115))
            grad.setColorAt(0.45, base)
            grad.setColorAt(1.0, base.darker(200))
        elif profile.shell_kind == "cardboard":
            grad.setColorAt(0.0, base.darker(110))
            grad.setColorAt(1.0, base.darker(175))
        else:
            grad.setColorAt(0.0, base)
            grad.setColorAt(1.0, base.darker(190))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)

        # Spine highlight groove on translucent plastic shells
        if profile.shell_kind in {"translucent_clear", "translucent_tint", "jewel_clear"} and depth > 3.5:
            seam_x = (x0 + x1) * 0.5
            painter.setPen(QPen(QColor(255, 255, 255, 48), 0.9))
            painter.drawLine(
                QPointF(seam_x, target.top() + depth * 0.16),
                QPointF(seam_x, target.bottom() - depth * 0.16),
            )
