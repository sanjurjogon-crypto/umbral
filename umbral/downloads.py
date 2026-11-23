from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .detect import _default_roots, _unique_roots
from .rom_rules import AMBIGUOUS_EXTENSIONS, rom_system, validate_rom
from .index import composite
from .models import Game
from .paths import data_dir
from .profiles import PROFILES, EmulatorProfile

PARTIAL_SUFFIXES = (
    ".part",
    ".crdownload",
    ".download",
    ".opdownload",
    ".!ut",
    ".aria2",
    ".tmp",
    ".partial",
    ".incomplete",
)

ROM_EXTENSIONS = {
    extension.lower()
    for profile in PROFILES
    for extension in profile.rom_extensions
}

RECENT_SECONDS = 60 * 60 * 72
PARTIAL_SECONDS = 60 * 60 * 24
STATE_FILE = "downloads_seen.json"


@dataclass
class Download:
    path: Path
    size: int
    partial: bool
    extension: str
    is_new: bool = True

    @property
    def size_text(self) -> str:
        value = float(self.size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                if unit == "B":
                    return f"{int(value)} B"
                return f"{value:.1f} {unit}"
            value /= 1024
        return ""


def _is_partial(path: Path) -> bool:
    return path.suffix.lower() in PARTIAL_SUFFIXES


def _final_extension(path: Path) -> str:
    stem = path.name
    for suffix in PARTIAL_SUFFIXES:
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return Path(stem).suffix.lower()


def _profile_for_extension(extension: str) -> EmulatorProfile | None:
    matches = [profile for profile in PROFILES if extension in profile.rom_extensions]
    if not matches:
        return None
    return min(matches, key=lambda profile: (profile.priority, profile.name))


def looks_like_rom(path: Path) -> bool:
    extension = _final_extension(path)
    if extension not in ROM_EXTENSIONS:
        return False
    if extension in AMBIGUOUS_EXTENSIONS:
        return validate_rom(path)
    return True


def load_state() -> dict[str, float]:
    path = data_dir() / STATE_FILE
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    state: dict[str, float] = {}
    for key, value in data.items():
        try:
            state[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return state


def save_state(state: dict[str, float]) -> None:
    path = data_dir() / STATE_FILE
    try:
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except OSError:
        pass


def scan_downloads(
    scan_folders: Iterable[str] | None = None,
    roots_override: Iterable[Path] | None = None,
    state: dict[str, float] | None = None,
    recent_seconds: int = RECENT_SECONDS,
) -> list[Download]:
    extra = [Path(folder) for folder in (scan_folders or []) if folder and Path(folder).exists()]
    roots = _unique_roots([*(roots_override or _default_roots()), *extra])
    known = state if state is not None else load_state()
    now = time.time()
    found: list[Download] = []
    seen: set[str] = set()

    index = composite(roots, max_depth=6)
    for entry in index.files:
        if entry.depth > 6:
            continue
        path = entry.path
        extension = _final_extension(path)
        partial = _is_partial(path)
        if not partial and extension not in ROM_EXTENSIONS:
            continue
        if not partial and not looks_like_rom(path):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        is_new = key not in known
        if partial:
            if now - stat.st_mtime > PARTIAL_SECONDS:
                continue
        elif not is_new and now - stat.st_mtime > recent_seconds:
            continue
        seen.add(key)
        found.append(
            Download(
                path=path,
                size=stat.st_size,
                partial=partial,
                extension=extension,
                is_new=is_new,
            )
        )
    found.sort(key=lambda item: (not item.partial, item.size), reverse=True)
    deduplicated: list[Download] = []
    seen_files: set[tuple[str, int]] = set()
    for item in found:
        signature = (item.path.name.lower(), item.size)
        if signature in seen_files:
            continue
        seen_files.add(signature)
        deduplicated.append(item)
    return deduplicated


def pending_downloads(
    scan_folders: Iterable[str] | None = None,
    games: list[Game] | None = None,
    state: dict[str, float] | None = None,
) -> list[Download]:
    finished_roms = {
        os.path.normcase(str(game.rom_path))
        for game in (games or [])
        if game.rom_path
    }
    result: list[Download] = []
    for download in scan_downloads(scan_folders, state=state):
        if not download.partial and os.path.normcase(str(download.path)) in finished_roms:
            continue
        result.append(download)
    return result


def mark_seen(downloads: Iterable[Download], state: dict[str, float] | None = None) -> None:
    current = state if state is not None else load_state()
    now = time.time()
    for download in downloads:
        current[os.path.normcase(str(download.path))] = now
    save_state(current)


def emulator_for(path: Path) -> EmulatorProfile | None:
    extension = _final_extension(path)
    if extension not in AMBIGUOUS_EXTENSIONS:
        return _profile_for_extension(extension)
    system = rom_system(path)
    if system is None:
        return None
    matches = [
        profile
        for profile in PROFILES
        if extension in profile.rom_extensions
        and (profile.system_key == system or system in profile.systems)
    ]
    if not matches:
        return None
    return min(matches, key=lambda profile: (profile.priority, profile.name))


def describe(download: Download) -> str:
    profile = emulator_for(download.path)
    system = profile.system if profile else "sistema desconocido"
    emulator = profile.name if profile else "sin emulador"
    state = "descargando" if download.partial else "lista para jugar"
    return f"{system} · {emulator} · {download.size_text} · {state}"
