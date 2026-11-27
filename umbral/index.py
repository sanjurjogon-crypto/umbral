from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

SKIP_DIRS = {
    "romfs",
    "exefs",
    ".hookshot_romfs",
    ".hookshot_exefs",
    "ps3_game",
    "usrdir",
    "nand",
    "sdmc",
    "cache",
    "shader",
    "shaders",
    "logs",
    "log",
    "node_modules",
    "site-packages",
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "virtualbox vms",
    "winsxs",
    "$recycle.bin",
    "system volume information",
    "update-old",
    "dump",
    "tas",
    "screenshots",
    "dist",
    "build",
    "target",
    "obj",
    "packages",
    "installer",
    "installers",
    "temp",
    "tmp",
    "steamapps",
    "_commonredist",
    "redist",
    "redistributables",
    "support",
    "directx",
    "dotnet",
    "prompts",
    "pipelines",
    "licenses",
    "license",
    "docs",
    "documentation",
    "readme",
    "saves",
    "save",
    "windows",
    "system32",
    "syswow64",
    "driverstore",
    "assembly",
    "windowsapps",
    "windows.old",
    "appdata",
    "programdata",
    "recovery",
    "perflogs",
    "msocache",
}

CACHE_TTL = 60.0
MAX_DEPTH = 9
MAX_FILES = 150_000
MAX_CACHED_ROOTS = 24


@dataclass(frozen=True)
class IndexedPath:
    path: Path
    depth: int


@dataclass
class FileIndex:
    files: list[IndexedPath] = field(default_factory=list)
    dirs: list[IndexedPath] = field(default_factory=list)


@dataclass
class _RootCache:
    built_at: float
    index: FileIndex


_CACHE: dict[tuple[str, int], _RootCache] = {}
_LOCK = threading.Lock()


def invalidate() -> None:
    with _LOCK:
        _CACHE.clear()


def _root_key(root: Path) -> str:
    try:
        return os.path.normcase(str(Path(root).resolve()))
    except OSError:
        return os.path.normcase(str(root))


def _walk_root(root: Path, max_depth: int, max_files: int) -> FileIndex:
    result = FileIndex()
    root = Path(root)
    if not root.exists():
        return result
    base_parts = len(root.parts)
    visited = 0
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=lambda _error: None):
        current = Path(dirpath)
        depth = len(current.parts) - base_parts
        result.dirs.append(IndexedPath(current, depth))
        if depth >= max_depth:
            dirnames[:] = []
        else:
            dirnames[:] = [
                name
                for name in dirnames
                if name.lower() not in SKIP_DIRS and not name.startswith(".")
            ]
        for name in filenames:
            visited += 1
            if visited > max_files:
                return result
            result.files.append(IndexedPath(current / name, depth + 1))
    return result


def root_index(root: Path, max_depth: int = MAX_DEPTH, max_files: int = MAX_FILES) -> FileIndex:
    key = (_root_key(root), max_depth)
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None and now - cached.built_at < CACHE_TTL:
            return cached.index
    built = _walk_root(Path(root), max_depth, max_files)
    with _LOCK:
        if len(_CACHE) >= MAX_CACHED_ROOTS:
            cutoff = now - CACHE_TTL * 5
            for stale in [item for item, entry in _CACHE.items() if entry.built_at < cutoff]:
                _CACHE.pop(stale, None)
            if len(_CACHE) >= MAX_CACHED_ROOTS:
                _CACHE.clear()
        _CACHE[key] = _RootCache(now, built)
    return built


def composite(roots: Iterable[Path], max_depth: int = MAX_DEPTH) -> FileIndex:
    combined = FileIndex()
    seen: set[str] = set()
    for root in roots:
        key = _root_key(Path(root))
        if key in seen:
            continue
        seen.add(key)
        index = root_index(Path(root), max_depth)
        combined.files.extend(index.files)
        combined.dirs.extend(index.dirs)
    return combined
