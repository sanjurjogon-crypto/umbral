from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path, PureWindowsPath

APP_NAME = "Umbral"
_MIGRATED = False


def path_key(value: str) -> str:
    try:
        return os.path.normcase(os.path.abspath(value))
    except OSError:
        return os.path.normcase(value)


def safe_path(value: str) -> PureWindowsPath | Path:
    if "\\" in value or (len(value) >= 2 and value[1] == ":"):
        return PureWindowsPath(value)
    return Path(value)


def cache_root() -> Path:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local)
    if os.name == "nt":
        return Path.home() / "AppData" / "Local"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches"
    xdg_cache = os.environ.get("XDG_CACHE_HOME", "").strip()
    return Path(xdg_cache) if xdg_cache else (Path.home() / ".cache")


def downloads_dir() -> Path:
    return Path.home() / "Downloads"


def _legacy_data_dir() -> Path:
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        base = Path(appdata)
    elif os.name == "nt":
        base = Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME", "").strip()
        base = Path(xdg_data) if xdg_data else (Path.home() / ".local" / "share")
    return base / APP_NAME


def _migrate_legacy_data(target: Path) -> None:
    global _MIGRATED
    if _MIGRATED:
        return
    _MIGRATED = True
    try:
        legacy = _legacy_data_dir()
        if legacy == target or not legacy.is_dir():
            return
        for name in (
            "library.json",
            "settings.json",
            "synopses.json",
            "cover_cache.json",
            "downloads_seen.json",
        ):
            src = legacy / name
            dst = target / name
            if src.is_file() and not dst.exists():
                shutil.copy2(src, dst)
        for folder in ("covers", "backdrops", "logs"):
            src_dir = legacy / folder
            dst_dir = target / folder
            if src_dir.is_dir():
                dst_dir.mkdir(parents=True, exist_ok=True)
                for src_file in src_dir.rglob("*"):
                    if src_file.is_file():
                        dst_file = dst_dir / src_file.relative_to(src_dir)
                        if not dst_file.exists():
                            dst_file.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(src_file, dst_file)
    except OSError:
        pass


def data_dir() -> Path:
    override = os.environ.get("UMBRAL_DATA_DIR", "").strip()
    path = Path(override) if override else (downloads_dir() / APP_NAME)
    path.mkdir(parents=True, exist_ok=True)
    if not override:
        _migrate_legacy_data(path)
    return path


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def covers_dir() -> Path:
    path = data_dir() / "covers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backdrops_dir() -> Path:
    path = data_dir() / "backdrops"
    path.mkdir(parents=True, exist_ok=True)
    return path


def usage_dir() -> Path:
    path = data_dir() / "uso"
    path.mkdir(parents=True, exist_ok=True)
    return path


def usage_file() -> Path:
    return usage_dir() / "estadisticas.json"


def backups_dir() -> Path:
    path = data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def library_file() -> Path:
    return data_dir() / "library.json"


def settings_file() -> Path:
    return data_dir() / "settings.json"


def executable_file_filter() -> str:
    if os.name == "nt":
        return "Ejecutables (*.exe);;Todos los archivos (*)"
    if sys.platform == "darwin":
        return "Aplicaciones y ejecutables (*.app *.sh *.command);;Todos los archivos (*)"
    return "Todos los archivos (*);;AppImage y scripts (*.AppImage *.sh *.x86_64 *.exe)"


def assets_dir() -> Path:
    return Path(__file__).resolve().parent / "assets"
