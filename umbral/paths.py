from __future__ import annotations

import os
import sys
from pathlib import Path, PureWindowsPath

APP_NAME = "Umbral"


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


def data_dir() -> Path:
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
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
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
