from __future__ import annotations

import re
from pathlib import Path

AMBIGUOUS_EXTENSIONS = frozenset(
    {
        ".iso",
        ".zip",
        ".7z",
        ".cue",
        ".chd",
        ".bin",
        ".md",
        ".crt",
        ".dsk",
        ".lha",
        ".rom",
        ".tap",
        ".cas",
    }
)


def is_ambiguous(path: str | Path) -> bool:
    return Path(path).suffix.lower() in AMBIGUOUS_EXTENSIONS


def path_hint(path: Path) -> str | None:
    parts = [part.lower() for part in path.parts]

    def has_word(word: str) -> bool:
        pattern = rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])"
        return any(re.search(pattern, part) for part in parts)

    def has_text(*words: str) -> bool:
        return any(word in part for part in parts for word in words)

    if has_word("ps3") or has_text("playstation 3"):
        return "ps3"
    if has_word("ps2") or has_text("playstation 2"):
        return "ps2"
    if has_word("psp"):
        return "psp"
    if has_word("psvita") or has_word("vita"):
        return "psvita"
    if has_word("ps1") or has_word("psx") or has_text("playstation"):
        return "ps1"
    if has_word("xbox360") or has_text("xbox 360"):
        return "xbox360"
    if has_word("xbox"):
        return "xbox"
    if has_word("switch2") or has_text("switch 2"):
        return "switch2"
    if has_word("switch"):
        return "switch"
    if has_word("wiiu") or has_text("wii u"):
        return "wiiu"
    if has_text("wii", "gamecube"):
        return "wii"
    if has_word("3ds"):
        return "3ds"
    if has_word("nds") or has_text("nintendo ds"):
        return "nds"
    if has_word("gba") or has_text("game boy advance"):
        return "gba"
    if has_word("gbc") or has_text("game boy color"):
        return "gbc"
    if has_word("gb") or has_text("game boy", "gameboy"):
        return "gb"
    if has_word("snes") or has_text("super nintendo"):
        return "snes"
    if has_word("nes") or has_text("nintendo entertainment"):
        return "nes"
    if has_word("n64") or has_text("nintendo 64"):
        return "n64"
    if has_word("saturn"):
        return "saturn"
    if has_word("dreamcast"):
        return "dreamcast"
    if has_word("genesis") or has_word("megadrive") or has_text("mega drive"):
        return "genesis"
    if has_word("mastersystem") or has_text("master system"):
        return "mastersystem"
    if has_word("gamegear") or has_text("game gear"):
        return "gamegear"
    if has_word("neogeo") or has_text("neo geo"):
        return "neogeo"
    if has_word("mame") or has_word("fbneo") or has_text("arcade"):
        return "arcade"
    if has_word("pce") or has_text("pc engine", "turbografx"):
        return "pce"
    if has_word("atari2600") or has_text("atari 2600"):
        return "atari2600"
    if has_word("c64") or has_text("commodore 64"):
        return "c64"
    if has_word("amiga"):
        return "amiga"
    if has_word("msx"):
        return "msx"
    if has_word("zx") or has_text("spectrum"):
        return "zx"
    if has_word("cpc") or has_text("amstrad"):
        return "cpc"
    return None


def plausible(path: str | Path, system_key: str) -> bool:
    if not is_ambiguous(path):
        return True
    hint = path_hint(Path(path))
    if hint is None:
        return False
    if system_key == "multi" or system_key == hint:
        return True
    if system_key == "genesis" and hint in {"mastersystem", "gamegear"}:
        return True
    if system_key == "arcade" and hint == "neogeo":
        return True
    return False
