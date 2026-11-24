from __future__ import annotations

import os
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


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".umbral")
    path = Path(base) / APP_NAME
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


def library_file() -> Path:
    return data_dir() / "library.json"


def settings_file() -> Path:
    return data_dir() / "settings.json"


def assets_dir() -> Path:
    return Path(__file__).resolve().parent / "assets"
