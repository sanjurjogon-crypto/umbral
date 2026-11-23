from __future__ import annotations

import re
import zipfile
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


SEGA_EXTENSIONS = frozenset({".bin", ".md", ".gen", ".sms", ".gg"})
ATARI_SIZES = frozenset({2048, 4096, 8192, 16384, 32768})
OTHER_ROM_EXTENSIONS = frozenset(
    {
        ".nes",
        ".sfc",
        ".smc",
        ".gba",
        ".gb",
        ".gbc",
        ".n64",
        ".z64",
        ".v64",
        ".nds",
        ".3ds",
        ".cci",
        ".cia",
        ".cxi",
        ".nsp",
        ".xci",
        ".nro",
        ".iso",
        ".rvz",
        ".wbfs",
        ".gcm",
        ".gcz",
        ".wud",
        ".wux",
        ".cso",
        ".pbp",
        ".gdi",
        ".cdi",
        ".chd",
        ".a26",
        ".vpk",
        ".d64",
        ".crt",
        ".tap",
        ".prg",
        ".adf",
        ".ipf",
        ".lha",
        ".rom",
        ".dsk",
        ".cas",
        ".pce",
    }
)

ZIP_EXTENSION_SYSTEMS = {
    ".nes": "nes",
    ".sfc": "snes",
    ".smc": "snes",
    ".gba": "gba",
    ".gb": "gb",
    ".gbc": "gbc",
    ".n64": "n64",
    ".z64": "n64",
    ".v64": "n64",
    ".nds": "nds",
    ".3ds": "3ds",
    ".cci": "3ds",
    ".cia": "3ds",
    ".cxi": "3ds",
    ".nsp": "switch",
    ".xci": "switch",
    ".nro": "switch",
    ".iso": "ps2",
    ".rvz": "wii",
    ".wbfs": "wii",
    ".gcm": "wii",
    ".gcz": "wii",
    ".wud": "wii",
    ".wux": "wii",
    ".cso": "psp",
    ".pbp": "psp",
    ".cue": "ps1",
    ".gdi": "dreamcast",
    ".cdi": "dreamcast",
    ".chd": "ps1",
    ".a26": "atari2600",
    ".vpk": "psvita",
    ".d64": "c64",
    ".crt": "c64",
    ".tap": "zx",
    ".prg": "c64",
    ".adf": "amiga",
    ".ipf": "amiga",
    ".lha": "amiga",
    ".rom": "msx",
    ".dsk": "cpc",
    ".cas": "msx",
    ".pce": "pce",
}


def sega_header(path: str | Path) -> bool:
    candidate = Path(path)
    try:
        with candidate.open("rb") as handle:
            head = handle.read(0x200)
            if len(head) >= 0x110 and head[0x100:0x104] == b"SEGA":
                marker = head[0x100:0x120]
                if any(
                    token in marker
                    for token in (b"MEGA DRIVE", b"GENESIS", b"32X", b"MEGA TECH")
                ):
                    return True
            for offset in (0x1FF0, 0x3FF0, 0x7FF0):
                handle.seek(offset)
                if handle.read(8) == b"TMR SEGA":
                    return True
    except OSError:
        return False
    return False


def crt_header(path: str | Path) -> bool:
    try:
        with Path(path).open("rb") as handle:
            return handle.read(16).startswith(b"C64 CARTRIDGE")
    except OSError:
        return False


def chd_header(path: str | Path) -> bool:
    try:
        with Path(path).open("rb") as handle:
            return handle.read(8) == b"MComprHD"
    except OSError:
        return False


def cue_is_valid(path: str | Path) -> bool:
    cue = Path(path)
    try:
        text = cue.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    for line in text.splitlines():
        match = re.match(r'\s*FILE\s+(?:"([^"]+)"|(\S+))\s+\S+', line, re.I)
        if not match:
            continue
        name = match.group(1) or match.group(2) or ""
        track = Path(name)
        if not track.is_absolute():
            track = cue.parent / track
        try:
            if track.is_file() and track.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


def zip_rom_system(path: str | Path) -> str | None:
    archive_path = Path(path)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                suffix = Path(info.filename).suffix.lower()
                if suffix in SEGA_EXTENSIONS:
                    with archive.open(info) as handle:
                        head = handle.read(0x200)
                    if len(head) >= 0x110 and head[0x100:0x104] == b"SEGA":
                        return "genesis"
                    continue
                system = ZIP_EXTENSION_SYSTEMS.get(suffix)
                if system:
                    return system
            hint = path_hint(archive_path)
            return hint if hint in {"arcade", "neogeo"} else None
    except (OSError, zipfile.BadZipFile):
        return None


def zip_has_rom(path: str | Path) -> bool:
    return zip_rom_system(path) is not None


def iso_system(path: str | Path) -> str | None:
    try:
        with Path(path).open("rb") as handle:
            head = handle.read(4 * 1024 * 1024)
    except OSError:
        return None
    if b"PS3_DISC.SFB" in head or b"PS3_GAME" in head:
        return "ps3"
    if b"PSP_GAME" in head:
        return "psp"
    if b"SYSTEM.CNF" in head and b"BOOT2" in head and b"cdrom0" in head:
        return "ps2"
    if b"PLAYSTATION" in head or b"BOOT = cdrom0" in head or b"BOOT=cdrom0" in head:
        return "ps1"
    if len(head) >= 0x1C:
        magic = head[0x18:0x1C]
        if magic in (b"\x5d\x1c\x9e\xa3", b"\xc2\x33\x9f\x3d"):
            return "wii"
    return None


def rom_system(path: str | Path) -> str | None:
    candidate = Path(path)
    suffix = candidate.suffix.lower()
    if suffix in SEGA_EXTENSIONS:
        if sega_header(candidate):
            return "genesis"
        if suffix == ".bin" and path_hint(candidate) == "atari2600":
            try:
                if candidate.stat().st_size in ATARI_SIZES:
                    return "atari2600"
            except OSError:
                return None
        return None
    if suffix == ".iso":
        return iso_system(candidate) or path_hint(candidate)
    if suffix == ".cue":
        if not cue_is_valid(candidate):
            return None
        return path_hint(candidate) or "ps1"
    if suffix == ".chd":
        return path_hint(candidate) if chd_header(candidate) else None
    if suffix == ".zip":
        content = zip_rom_system(candidate)
        if content is None:
            return None
        hint = path_hint(candidate)
        if content in {"ps2", "ps1"}:
            return hint
        return content
    if suffix == ".crt":
        return "c64" if crt_header(candidate) else None
    return path_hint(candidate)


def validate_rom(path: str | Path, system_key: str = "") -> bool:
    candidate = Path(path)
    try:
        if not candidate.is_file():
            return False
    except OSError:
        return False
    if not is_ambiguous(candidate):
        return True
    detected = rom_system(candidate)
    if detected is None:
        if system_key == "atari2600" and candidate.suffix.lower() == ".bin":
            try:
                return candidate.stat().st_size in ATARI_SIZES
            except OSError:
                return False
        return False
    if not system_key or system_key == "multi" or system_key == detected:
        return True
    if system_key == "genesis" and detected in {"mastersystem", "gamegear"}:
        return True
    if system_key == "arcade" and detected == "neogeo":
        return True
    return False


def plausible(path: str | Path, system_key: str) -> bool:
    return validate_rom(path, system_key)
