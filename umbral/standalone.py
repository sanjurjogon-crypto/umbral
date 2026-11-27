from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .detect import _default_roots, _unique_roots, clean_title
from .index import composite
from .models import Game, slugify
from .paths import data_dir
from .stores import steam_roots

SYSTEM_DIR_NAMES = {
    "windows",
    "system32",
    "syswow64",
    "winsxs",
    "winsxs",
    "driverstore",
    "assembly",
}

GENERIC_FOLDERS = {
    "bin",
    "binaries",
    "win64",
    "win32",
    "x64",
    "x86",
    "release",
    "released",
    "build",
    "game",
    "games",
    "app",
    "application",
    "program",
    "programs",
    "runtime",
    "system",
    "data",
    "win",
    "linux",
    "mac",
    "macos",
    "osx",
}

EXCLUDED_EXE_NAMES = {
    "python.exe",
    "pythonw.exe",
    "pip.exe",
    "pip3.exe",
    "git.exe",
    "node.exe",
    "npm.exe",
    "code.exe",
    "chrome.exe",
    "firefox.exe",
    "msedge.exe",
    "explorer.exe",
    "notepad.exe",
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "7z.exe",
    "7zfm.exe",
    "winrar.exe",
    "vlc.exe",
    "spotify.exe",
    "discord.exe",
    "steam.exe",
    "steamwebhelper.exe",
    "epicgameslauncher.exe",
    "goggalaxy.exe",
    "rpcs3.exe",
    "azahar.exe",
    "lichii.exe",
    "fritchii.exe",
    "ryujinx.exe",
    "yuzu.exe",
    "cemu.exe",
    "dolphin.exe",
    "dolphin-emu.exe",
    "pcsx2.exe",
    "pcsx2-qt.exe",
    "duckstation-qt-x64-releaseltcg.exe",
    "ppssppwindows64.exe",
    "ppssppwindows.exe",
    "melonds.exe",
    "mgba.exe",
    "retroarch.exe",
    "lime3ds.exe",
    "citra.exe",
    "hookshot.exe",
    "umbral.exe",
    "unins000.exe",
    "unins001.exe",
    "unitycrashhandler64.exe",
    "unitycrashhandler32.exe",
    "crashreportclient.exe",
    "ue4prereqsetup_x64.exe",
    "ue5prereqsetup_x64.exe",
    "vcredist_x64.exe",
    "vcredist_x86.exe",
    "dxsetup.exe",
    "dxwebsetup.exe",
    "oalinst.exe",
    "bootstrap.exe",
    "eglantine.exe",
    "eden-cli.exe",
    "eden.exe",
    "sudachi.exe",
    "suyu.exe",
    "torzu.exe",
    "nx2-precompile.exe",
    "hookshotbuilder.exe",
    "abdownloadmanager.exe",
    "localsend.exe",
    "wireshark.exe",
    "vlc.exe",
    "vlc-cache-gen.exe",
    "virtualbox.exe",
    "python",
    "python3",
    "pip",
    "pip3",
    "git",
    "node",
    "npm",
    "chrome",
    "firefox",
    "steam",
    "rpcs3",
    "azahar",
    "ryujinx",
    "yuzu",
    "suyu",
    "eden",
    "sudachi",
    "cemu",
    "dolphin-emu",
    "pcsx2",
    "pcsx2-qt",
    "duckstation",
    "duckstation-qt",
    "ppsspp",
    "melonds",
    "mgba",
    "mgba-qt",
    "retroarch",
    "lime3ds",
    "citra",
    "hookshot",
    "umbral",
    "umbral-linux-x86_64",
}

EXCLUDED_NAME_PATTERNS = (
    "setup",
    "install",
    "unins",
    "uninstall",
    "prereq",
    "redist",
    "vcredist",
    "dxsetup",
    "dotnet",
    "crash",
    "report",
    "diagnostic",
    "updater",
    "patcher",
    "update",
    "benchmark",
)

EXCLUDED_COMPANIES = {
    "microsoft corporation",
    "microsoft",
    "nvidia corporation",
    "cisco systems, inc.",
    "cisco systems",
    "oracle corporation",
    "oracle and/or its affiliates",
    "wireshark foundation",
    "wireshark development team",
    "videolan",
    "portableapps.com",
    "google llc",
    "google",
    "mozilla",
    "docker inc.",
    "jetbrains s.r.o.",
    "opencode",
    "openchamber",
    "deepseek",
    "ab download manager",
    "localsend",
    "tien do nam",
    "valve corporation",
}

INSTALLER_FOLDER_HINTS = {
    "launchers e instaladores",
    "launchers",
    "instaladores",
    "installers",
    "installer",
    "programas",
}

ONLINE_LABELS = {
    "steam": "Steam",
    "steam-local": "Steam (instalado)",
    "itch": "itch.io",
    "pcgamingwiki": "PCGamingWiki",
}

GENERIC_TITLES = {
    "",
    "game",
    "games",
    "launcher",
    "application",
    "program",
    "setup",
    "install",
    "uninstall",
    "unity",
    "unreal",
    "unreal engine",
    "epic games",
    "steam",
    "configuration",
    "settings",
    "crash handler",
    "bug report",
    "updater",
    "patcher",
    "test",
    "demo",
    "unrealgame",
    "bootstrap packaged game",
    "bootstrappackagedgame",
    "third person bp game template",
    "blank",
    "new project",
    "windows",
    "application",
    "mono",
}

FOLDER_MARKERS = {
    "data",
    "content",
    "assets",
    "saves",
    "save",
    "config",
    "engine",
    "binaries",
    "paks",
    "mods",
    "resources",
    "game",
    "www",
    "locales",
    "streamingassets",
}

PUBLISHER_TAG_PATTERN = re.compile(
    r"[\s._-]*(steamrip|zeigames|itch\.io|itch|fitgirl|doge|gog|epic|"
    r"repack|proper|multi\d*|cracked|pre[- ]?installed)\b.*$",
    re.I,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 Umbral/0.1"
)
CACHE_TTL = timedelta(days=7)
CACHE_FILE = "standalone_cache.json"


@dataclass
class StandaloneCandidate:
    executable: Path
    game_root: Path
    working_dir: Path
    title: str
    company: str = ""
    description: str = ""
    engine: str = ""
    score: int = 0
    reason: str = ""
    online_status: str = "unverified"
    online_title: str = ""
    online_url: str = ""
    steam_app_id: str = ""
    warning: str = ""

    @property
    def confidence_label(self) -> str:
        if self.score >= 5:
            return "Alta"
        if self.score >= 2:
            return "Media"
        return "Baja"

    @property
    def source_label(self) -> str:
        return ONLINE_LABELS.get(self.online_status, "")

    @property
    def display_title(self) -> str:
        if self.online_ok and self.online_title:
            return self.online_title
        return self.title

    @property
    def online_ok(self) -> bool:
        return self.online_status in {"steam", "steam-local", "itch", "pcgamingwiki"}

    def to_game(self) -> Game:
        digest = hashlib.sha1(str(self.executable).lower().encode("utf-8")).hexdigest()[:8]
        title = self.display_title
        subtitle = "PC"
        if self.online_status == "itch":
            subtitle = "PC · itch.io"
        elif self.online_status == "pcgamingwiki":
            subtitle = "PC · PCGamingWiki"
        description = self.description or (
            f"Juego independiente detectado en {self.game_root}. "
            "Umbral lo lanzará directamente, sin emulador."
        )
        notes = []
        if self.engine:
            notes.append(f"Motor: {self.engine}")
        if self.online_title:
            notes.append(f"Verificado en {self.source_label}: {self.online_title}")
        elif self.online_status == "not_found":
            notes.append("Sin coincidencia online: revisa que sea un juego antes de añadirlo")
        elif self.online_status == "offline":
            notes.append("No se pudo comprobar online")
        if self.steam_app_id:
            notes.append(f"AppID de Steam: {self.steam_app_id}")
        return Game(
            id=slugify(f"pc-{title}-{digest}"),
            title=title,
            system="PC",
            system_key="pc",
            subtitle=subtitle,
            description=description,
            executable=str(self.executable),
            arguments=[],
            working_dir=str(self.working_dir),
            rom_path="",
            emulator="Standalone",
            accent="#E9B949",
            source="standalone",
            notes=" · ".join(notes),
        )


@dataclass
class _RawCandidate:
    executable: Path
    game_root: Path
    working_dir: Path
    title: str
    info: dict[str, str]
    engine: str
    engine_score: int
    folder_score: int
    size: int
    loose: bool

    @property
    def score(self) -> int:
        value = self.engine_score + self.folder_score
        if self.info.get("ProductName"):
            value += 1
        if self.info.get("FileDescription"):
            value += 1
        if self.size >= 20_000_000:
            value += 1
        if self.size >= 200_000_000:
            value += 1
        if self.size >= 1_000_000_000:
            value += 1
        if "launcher" in self.executable.name.lower():
            value -= 1
        if self.loose and self.size < 20_000_000:
            value -= 2
        if _installer_folder(self.exe_parent):
            value -= 2
        if not self.loose and self.game_root.name.lower().endswith(".exe"):
            value -= 3
        return value

    @property
    def exe_parent(self) -> Path:
        return self.executable.parent

    @property
    def rank(self) -> tuple[int, int, bool]:
        return (self.score, self.size, "launcher" not in self.executable.name.lower())


def _same_path(a: Path, b: Path) -> bool:
    try:
        left = os.path.normcase(str(a.resolve()))
        right = os.path.normcase(str(b.resolve()))
    except OSError:
        left = os.path.normcase(str(a.absolute()))
        right = os.path.normcase(str(b.absolute()))
    return left == right


def _prefixes(paths: list[Path]) -> list[str]:
    prefixes: list[str] = []
    for path in paths:
        try:
            prefixes.append(os.path.normcase(str(path.resolve())))
        except OSError:
            prefixes.append(os.path.normcase(str(path.absolute())))
    return prefixes


def _under_prefix(path: Path, prefixes: list[str]) -> bool:
    key = os.path.normcase(str(path))
    return any(key == prefix or key.startswith(prefix + os.sep) for prefix in prefixes)


def _system_prefixes() -> list[str]:
    if os.name != "nt":
        roots = [Path("/usr"), Path("/bin"), Path("/sbin"), Path("/lib"), Path("/lib64"), Path("/snap"), Path("/var/lib/flatpak")]
        prefixes: list[str] = []
        for root in roots:
            try:
                prefixes.append(os.path.normcase(str(root.resolve())))
            except OSError:
                prefixes.append(os.path.normcase(str(root)))
        return prefixes
    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    try:
        return [os.path.normcase(str(Path(system_root).resolve()))]
    except OSError:
        return [os.path.normcase(system_root)]


def _is_elf_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


def _is_candidate_executable(path: Path) -> bool:
    suffix = path.suffix.lower()
    if os.name == "nt":
        return suffix == ".exe"
    if suffix in {".appimage", ".x86_64", ".sh", ".exe"}:
        return True
    if suffix in {".so", ".dll", ".pak", ".txt", ".json", ".xml", ".png", ".jpg", ".svg", ".md", ".py"}:
        return False
    return os.access(path, os.X_OK) or _is_elf_binary(path)


def _walk_executables(
    roots: list[Path],
    exclude_dirs: list[Path],
    max_depth: int = 9,
    max_executables: int = 800,
):
    excluded = _prefixes(exclude_dirs)
    system = _system_prefixes()
    index = composite(roots, max_depth=max_depth)
    found = 0
    seen: set[str] = set()
    for entry in index.files:
        if entry.depth > max_depth:
            continue
        path = entry.path
        if not _is_candidate_executable(path):
            continue
        if _under_prefix(path, excluded) or _under_prefix(path, system):
            continue
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        found += 1
        if found > max_executables:
            return
        yield path


def _query_version_string(buffer, key: str) -> str:
    try:
        pointer = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not ctypes.windll.version.VerQueryValueW(
            buffer, key, ctypes.byref(pointer), ctypes.byref(length)
        ):
            return ""
        if not pointer.value:
            return ""
        return ctypes.wstring_at(pointer.value).strip()
    except (AttributeError, OSError, ValueError):
        return ""


def _file_version_info(path: Path) -> dict[str, str]:
    if os.name != "nt":
        return {}
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return {}
        buffer = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buffer):
            return {}
    except (AttributeError, OSError, ValueError):
        return {}

    translations: list[tuple[int, int]] = []
    try:
        pointer = ctypes.c_void_p()
        length = ctypes.c_uint()
        if ctypes.windll.version.VerQueryValueW(
            buffer, r"\VarFileInfo\Translation", ctypes.byref(pointer), ctypes.byref(length)
        ) and pointer.value:
            count = length.value // 2
            data = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_ushort * count)).contents
            for index in range(0, count - 1, 2):
                translations.append((int(data[index]), int(data[index + 1])))
    except (OSError, ValueError):
        translations = []

    if not translations:
        translations = [(0x0409, 0x04B0), (0x0409, 0x04E4), (0x0C0A, 0x04B0), (0x0C0A, 0x04E4)]

    info: dict[str, str] = {}
    for language, codepage in translations[:6]:
        prefix = f"\\StringFileInfo\\{language:04x}{codepage:04x}\\"
        for name in ("ProductName", "FileDescription", "CompanyName", "OriginalFilename"):
            if name in info:
                continue
            value = _query_version_string(buffer, prefix + name)
            if value:
                info[name] = value
    return info


def _engine_info(folder: Path) -> tuple[str, int, Path]:
    roots = [folder]
    parent = folder.parent
    if parent != folder:
        roots.append(parent)
    if folder.name.lower() in {"win64", "win32", "x64", "x86"} and parent.parent != parent:
        if parent.name.lower() in {"binaries", "bin"}:
            roots.append(parent.parent)
            if parent.parent.parent != parent.parent:
                roots.append(parent.parent.parent)
    for level in range(1, 4):
        candidate = folder
        for _ in range(level):
            candidate = candidate.parent
            if candidate == candidate.parent:
                break
        if candidate not in roots:
            roots.append(candidate)

    best = ("", 0, folder)
    for root in roots:
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        names = {entry.name.lower(): entry for entry in entries}
        markers: list[str] = []
        score = 0
        if (
            "unityplayer.dll" in names
            or "gameassembly.dll" in names
            or any(name.endswith("_data") and names[name].is_dir() for name in names)
        ):
            markers.append("Unity")
            score += 2
        if (
            "engine" in names and names["engine"].is_dir()
            or any(name.endswith(".pak") for name in names)
            or (root / "Content" / "Paks").is_dir()
            or (root / "Binaries" / "Win64").is_dir()
        ):
            markers.append("Unreal")
            score += 2
        if any(name.endswith(".pck") for name in names):
            markers.append("Godot")
            score += 2
        if "steam_api64.dll" in names or "steam_api.dll" in names or "steam_appid.txt" in names:
            markers.append("Steam")
            score += 1
        if any(name.startswith("goggame-") for name in names):
            markers.append("GOG")
            score += 1
        if "eossdk-win64-shipping.dll" in names or "epiconlineservices" in names:
            markers.append("Epic")
            score += 1
        if markers and score > best[1]:
            best = (" · ".join(dict.fromkeys(markers)), score, root)
    return best


def _folder_score(root: Path) -> int:
    try:
        names = {entry.name.lower() for entry in root.iterdir() if entry.is_dir()}
    except OSError:
        return 0
    return 1 if names & FOLDER_MARKERS else 0


def _valid_title(value: str) -> str:
    text = re.sub(r"[®™©]", "", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    lowered = text.lower()
    if not text or lowered in GENERIC_TITLES or len(text) < 2:
        return ""
    if lowered.startswith("microsoft "):
        return ""
    if re.search(r"\b(launcher|crash handler|updater|installer|setup)\b", text, re.I):
        return ""
    if re.search(r"\b(installer|setup|portable)\b", text, re.I) and text.lower().endswith(
        ("exe", "installer")
    ):
        return ""
    return text


def _clean_folder_title(name: str) -> str:
    text = PUBLISHER_TAG_PATTERN.sub("", name or "")
    text = re.sub(r"[\s._-]*v?\d+(?:\.\d+)+.*$", "", text)
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -._")
    return text


def _title_for(info: dict[str, str], executable: Path, game_root: Path, loose: bool) -> str:
    if not loose:
        folder_title = _valid_title(_clean_folder_title(game_root.name))
        if folder_title:
            return folder_title

    for key in ("ProductName", "FileDescription"):
        value = _valid_title(info.get(key, ""))
        if value and value.lower() in GENERIC_TITLES:
            continue
        if value and _looks_like_engine_placeholder(value):
            continue
        if value:
            return value

    stem_title = _valid_title(_clean_folder_title(executable.stem))
    if stem_title and not _looks_like_engine_placeholder(stem_title):
        return stem_title

    if not loose:
        folder_title = _valid_title(_clean_folder_title(game_root.name))
        if folder_title:
            return folder_title
    return clean_title(executable.stem)


def _looks_like_engine_placeholder(value: str) -> bool:
    lowered = value.lower().strip()
    return (
        lowered in GENERIC_TITLES
        or "shipping" in lowered
        or lowered.startswith("bootstrap")
        or lowered.endswith("win64")
        or lowered.endswith("win32")
        or lowered.endswith("-win")
        or re.fullmatch(r"(ue4|ue5|unreal).*", lowered) is not None
    )


def _infer_game_root(exe_parent: Path, engine_root: Path, roots: list[Path]) -> Path:
    if any(_same_path(exe_parent, root) for root in roots):
        return exe_parent
    if engine_root and not _same_path(engine_root, exe_parent):
        return engine_root
    if exe_parent.name.lower() in GENERIC_FOLDERS:
        candidate = exe_parent.parent
        if not any(_same_path(candidate, root) for root in roots):
            return candidate
    return exe_parent


def _reason(raw: _RawCandidate) -> str:
    bits: list[str] = []
    if raw.engine:
        bits.append(raw.engine)
    if raw.info.get("ProductName"):
        bits.append(f"ProductName: {raw.info['ProductName']}")
    if raw.info.get("CompanyName"):
        bits.append(raw.info["CompanyName"])
    if raw.folder_score:
        bits.append("carpeta con datos del juego")
    if raw.size:
        bits.append(f"{raw.size / 1_000_000:.0f} MB")
    return " · ".join(bits) or "Pocas señales de que sea un juego"


def _is_excluded_exe(name: str) -> bool:
    lower = name.lower()
    if lower in EXCLUDED_EXE_NAMES:
        return True
    return any(pattern in lower for pattern in EXCLUDED_NAME_PATTERNS)


def _company_excluded(company: str) -> bool:
    return (company or "").strip().lower() in EXCLUDED_COMPANIES


def _installer_folder(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return bool(parts & INSTALLER_FOLDER_HINTS)


def _read_steam_library() -> dict[str, dict[str, Any]]:
    installed: dict[str, dict[str, Any]] = {}
    for library in steam_roots():
        steamapps = library / "steamapps"
        if not steamapps.is_dir():
            continue
        common = steamapps / "common"
        for manifest in steamapps.glob("appmanifest_*.acf"):
            try:
                text = manifest.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            name_match = re.search(r'"name"\s*"([^"]+)"', text)
            dir_match = re.search(r'"installdir"\s*"([^"]+)"', text)
            id_match = re.search(r'"appid"\s*"(\d+)"', text)
            if not name_match or not dir_match:
                continue
            name = name_match.group(1).strip()
            folder = common / dir_match.group(1)
            if not folder.is_dir():
                continue
            key = _normalize_title(name)
            if key:
                installed[key] = {
                    "title": name,
                    "folder": folder,
                    "app_id": id_match.group(1) if id_match else "",
                }
    return installed


def _steam_local_match(title: str, library: dict) -> dict | None:
    key = _normalize_title(title)
    if not key:
        return None
    if key in library:
        entry = library[key]
        return {
            "status": "steam-local",
            "title": entry["title"],
            "url": f"https://store.steampowered.com/app/{entry['app_id']}/"
            if entry.get("app_id")
            else "",
            "app_id": entry.get("app_id", ""),
        }
    for library_key, entry in library.items():
        if _title_match(title, entry["title"]):
            return {
                "status": "steam-local",
                "title": entry["title"],
                "url": f"https://store.steampowered.com/app/{entry['app_id']}/"
                if entry.get("app_id")
                else "",
                "app_id": entry.get("app_id", ""),
            }
    return None


def discover_standalone_games(
    scan_folders: Iterable[str] | None = None,
    exclude_executables: Iterable[str] | None = None,
    exclude_dirs: Iterable[str] | None = None,
    include_steam: bool = True,
) -> list[StandaloneCandidate]:
    extra_roots = [Path(folder) for folder in (scan_folders or []) if folder and Path(folder).exists()]
    roots = _unique_roots([*_default_roots(), *extra_roots])
    excluded_executables = {
        os.path.normcase(str(Path(value).resolve()))
        for value in (exclude_executables or [])
        if value
    }
    excluded_dirs: list[Path] = []
    for value in exclude_dirs or []:
        if not value:
            continue
        path = Path(value)
        if path.exists():
            excluded_dirs.append(path.resolve())
    if include_steam:
        excluded_dirs.extend(steam_roots())

    grouped: dict[str, _RawCandidate] = {}
    for executable in _walk_executables(roots, excluded_dirs):
        key = os.path.normcase(str(executable))
        if key in excluded_executables:
            continue
        if _is_excluded_exe(executable.name):
            continue
        parts = {part.lower() for part in executable.parts}
        if parts & {"system32", "syswow64", "winsxs", "driverstore"}:
            continue
        if _installer_folder(executable) and "videojuegos" not in parts:
            continue

        try:
            size = executable.stat().st_size
        except OSError:
            continue
        if size < 262_144:
            continue

        info = _file_version_info(executable)
        if _company_excluded(info.get("CompanyName", "")):
            continue

        exe_parent = executable.parent
        engine, engine_score, engine_root = _engine_info(exe_parent)
        folder_score = _folder_score(engine_root if engine_score else exe_parent)
        loose = any(_same_path(exe_parent, root) for root in roots)
        game_root = _infer_game_root(exe_parent, engine_root, roots)

        has_identity = bool(info.get("ProductName"))
        if engine_score == 0 and not has_identity and folder_score == 0 and size < 5_000_000:
            continue
        if engine_score == 0 and not folder_score and size < 20_000_000 and not has_identity:
            continue
        if loose and engine_score == 0 and folder_score == 0:
            continue

        title = _title_for(info, executable, game_root, loose)
        if not title or title.lower() in GENERIC_TITLES:
            continue

        working_dir = engine_root if engine_score and not _same_path(engine_root, exe_parent) else exe_parent
        raw = _RawCandidate(
            executable=executable,
            game_root=game_root,
            working_dir=working_dir,
            title=title,
            info=info,
            engine=engine,
            engine_score=engine_score,
            folder_score=folder_score,
            size=size,
            loose=loose,
        )
        if raw.score < 2:
            continue
        group_key = str(executable).lower() if loose else str(game_root).lower()
        existing = grouped.get(group_key)
        if existing is None or raw.rank > existing.rank:
            grouped[group_key] = raw

    candidates: list[StandaloneCandidate] = []
    seen_titles: set[str] = set()
    for raw in sorted(grouped.values(), key=lambda item: -item.rank[0]):
        title_key = _normalize_title(raw.title)
        if not title_key:
            continue
        compact = title_key.replace(" ", "")
        if compact in seen_titles:
            continue
        seen_titles.add(compact)
        candidates.append(
            StandaloneCandidate(
                executable=raw.executable,
                game_root=raw.game_root,
                working_dir=raw.working_dir,
                title=raw.title,
                company=raw.info.get("CompanyName", ""),
                description=(
                    raw.info.get("FileDescription", "")
                    if raw.info.get("FileDescription", "").lower() != raw.title.lower()
                    else ""
                ),
                engine=raw.engine,
                score=raw.score,
                reason=_reason(raw),
            )
        )
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.title.lower()))
    return candidates[:60]


def _normalize_title(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _title_match(left: str, right: str) -> bool:
    a = _normalize_title(left)
    b = _normalize_title(right)
    if not a or not b:
        return False
    if a == b:
        return True
    compact_a = a.replace(" ", "")
    compact_b = b.replace(" ", "")
    if compact_a == compact_b:
        return True
    if len(compact_a) < 4 or len(compact_b) < 4:
        return False
    if compact_a in compact_b or compact_b in compact_a:
        shorter, longer = (
            (compact_a, compact_b) if len(compact_a) <= len(compact_b) else (compact_b, compact_a)
        )
        return len(shorter) / len(longer) >= 0.6
    return False


def _request_json(url: str) -> dict:
    from .net import ssl_context

    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=5, context=ssl_context()) as response:
        payload = response.read(512_000)
    data = json.loads(payload.decode("utf-8", errors="replace"))
    return data if isinstance(data, dict) else {}


def _request_text(url: str, limit: int = 400_000) -> str:
    from .net import ssl_context

    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(request, timeout=5, context=ssl_context()) as response:
        return response.read(limit).decode("utf-8", errors="replace")


def _check_steam(title: str) -> tuple[dict | None, bool]:
    url = (
        "https://store.steampowered.com/api/storesearch/"
        f"?term={quote(title, safe='')}&cc=ES&l=spanish"
    )
    try:
        data = _request_json(url)
    except (URLError, TimeoutError, OSError, ValueError):
        return None, True
    items = data.get("items", [])
    if not isinstance(items, list):
        return None, False
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        app_id = item.get("id")
        if app_id and _title_match(title, name):
            return {
                "status": "steam",
                "title": name,
                "url": f"https://store.steampowered.com/app/{app_id}/",
                "app_id": str(app_id),
            }, False
    return None, False


def _check_itch(title: str) -> tuple[dict | None, bool]:
    url = f"https://itch.io/search?q={quote(title, safe='')}&type=games"
    try:
        html = _request_text(url)
    except (URLError, TimeoutError, OSError, ValueError):
        return None, True
    pattern = re.compile(
        r'<a href="(?P<url>https://[^"]+\.itch\.io/[^"]+)"[^>]*'
        r'class="title game_link"[^>]*>(?P<name>[^<]+)</a>',
        re.I,
    )
    for match in pattern.finditer(html):
        name = _html_unescape(match.group("name")).strip()
        if name and _title_match(title, name):
            return {"status": "itch", "title": name, "url": match.group("url")}, False
    return None, False


def _check_pcgamingwiki(title: str) -> tuple[dict | None, bool]:
    url = (
        "https://www.pcgamingwiki.com/w/api.php?action=query&list=search"
        f"&srsearch={quote(title, safe='')}&format=json&srlimit=5"
    )
    try:
        data = _request_json(url)
    except (URLError, TimeoutError, OSError, ValueError):
        return None, True
    query = data.get("query", {})
    search = query.get("search", []) if isinstance(query, dict) else []
    if not isinstance(search, list):
        return None, False
    for item in search:
        if not isinstance(item, dict):
            continue
        name = str(item.get("title", ""))
        if _title_match(title, name):
            page = quote(name.replace(" ", "_"), safe="")
            return {
                "status": "pcgamingwiki",
                "title": name,
                "url": f"https://www.pcgamingwiki.com/wiki/{page}",
            }, False
    return None, False


def _html_unescape(text: str) -> str:
    return (
        text.replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#039;", "'")
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )


def _verify_one(title: str, steam_library: dict | None = None) -> dict:
    local = _steam_local_match(title, steam_library or {})
    if local:
        return local

    steam, steam_error = _check_steam(title)
    if steam:
        return steam
    itch, itch_error = _check_itch(title)
    if itch:
        return itch
    wiki, wiki_error = _check_pcgamingwiki(title)
    if wiki:
        return wiki
    if steam_error and itch_error and wiki_error:
        return {"status": "offline", "title": "", "url": "", "app_id": ""}
    return {"status": "not_found", "title": "", "url": "", "app_id": ""}


def _load_cache() -> dict:
    path = data_dir() / CACHE_FILE
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    path = data_dir() / CACHE_FILE
    try:
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except OSError:
        pass


def _cache_valid(entry: dict) -> bool:
    try:
        checked = datetime.fromisoformat(str(entry.get("checked_at", "")))
    except ValueError:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - checked < CACHE_TTL


def _apply(candidate: StandaloneCandidate, entry: dict) -> None:
    candidate.online_status = str(entry.get("status", "not_found"))
    candidate.online_title = str(entry.get("title", ""))
    candidate.online_url = str(entry.get("url", ""))
    candidate.steam_app_id = str(entry.get("app_id", ""))


def verify_candidates(candidates: list[StandaloneCandidate], limit: int = 20) -> int:
    cache = _load_cache()
    steam_library = _read_steam_library()
    pending: list[StandaloneCandidate] = []
    for candidate in candidates:
        key = _normalize_title(candidate.title)
        entry = cache.get(key)
        local = _steam_local_match(candidate.title, steam_library)
        if local:
            _apply(candidate, local)
            continue
        if isinstance(entry, dict) and _cache_valid(entry):
            _apply(candidate, entry)
            continue
        pending.append(candidate)

    pending = [candidate for candidate in pending if candidate.online_status == "unverified"][:limit]
    if not pending:
        _save_cache(cache)
        return 0

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(lambda candidate: _verify_one(candidate.title, steam_library), pending)
        )

    for candidate, result in zip(pending, results):
        _apply(candidate, result)
        if result.get("status") not in {"offline", "unverified"}:
            cache[_normalize_title(candidate.title)] = {
                **result,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
    _save_cache(cache)
    return len(pending)


def open_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    try:
        import webbrowser

        return webbrowser.open(url)
    except OSError:
        return False
