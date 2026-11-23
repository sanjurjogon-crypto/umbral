from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .models import Game, slugify

STEAM_ACCENT = "#66c0f4"
EPIC_ACCENT = "#c7c9cc"

STEAM_TOOL_NAMES = (
    "steamworks common redistributables",
    "steam linux runtime",
    "proton",
    "steamvr",
    "steam vr",
)


def _is_steam_tool(name: str) -> bool:
    lowered = name.strip().lower()
    return any(part in lowered for part in STEAM_TOOL_NAMES)


def _vdf_library_paths(text: str) -> list[Path]:
    raw_paths = [match.group(1) for match in re.finditer(r'"path"\s*"([^"]+)"', text)]
    raw_paths += [
        match.group(1)
        for match in re.finditer(r'"\d+"\s*"([^"]+)"', text)
        if ":" in match.group(1) or match.group(1).startswith("\\\\")
    ]
    paths: list[Path] = []
    for raw in raw_paths:
        extra = Path(raw.replace("\\\\", "\\"))
        if extra.is_dir() and extra not in paths:
            paths.append(extra)
    return paths


def steam_roots() -> list[Path]:
    candidates: list[Path] = []
    try:
        import winreg

        registry_keys = (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        )
        for root, subkey, value_name in registry_keys:
            try:
                with winreg.OpenKey(root, subkey) as handle:
                    value, _ = winreg.QueryValueEx(handle, value_name)
                    if value and Path(str(value)) not in candidates:
                        candidates.append(Path(str(value)))
            except (OSError, FileNotFoundError):
                continue
    except ImportError:
        pass

    for base in (
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
        Path(r"C:\Steam"),
    ):
        if base not in candidates:
            candidates.append(base)

    libraries: list[Path] = []
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        steamapps = candidate / "steamapps"
        if not steamapps.is_dir():
            continue
        if candidate not in libraries:
            libraries.append(candidate)
        vdf = steamapps / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for extra in _vdf_library_paths(text):
            if extra not in libraries:
                libraries.append(extra)
    return libraries


def _acf_value(text: str, key: str) -> str:
    match = re.search(rf'"{re.escape(key)}"\s*"([^"]*)"', text)
    return match.group(1).strip() if match else ""


def steam_games() -> list[Game]:
    games: dict[str, Game] = {}
    roots = steam_roots()
    steam_exe = next(
        (root / "steam.exe" for root in roots if (root / "steam.exe").is_file()),
        None,
    )
    if steam_exe is None:
        return []
    for library in roots:
        steamapps = library / "steamapps"
        common = steamapps / "common"
        if not steamapps.is_dir():
            continue
        for manifest in steamapps.glob("appmanifest_*.acf"):
            try:
                text = manifest.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            app_id = _acf_value(text, "appid")
            name = _acf_value(text, "name")
            install_dir = _acf_value(text, "installdir")
            if not app_id or not name or not install_dir:
                continue
            if _is_steam_tool(name):
                continue
            folder = common / install_dir
            if not folder.is_dir():
                continue
            if app_id in games:
                continue
            games[app_id] = Game(
                id=slugify(f"pc-steam-{app_id}"),
                title=name,
                system="Steam",
                system_key="steam",
                subtitle="Steam",
                description=f"Juego de Steam instalado en {folder}.",
                executable=str(steam_exe),
                arguments=["-applaunch", app_id],
                working_dir=str(steam_exe.parent),
                rom_path="",
                emulator="Steam",
                accent=STEAM_ACCENT,
                source="steam",
                notes=f"AppID de Steam: {app_id}",
            )
    return list(games.values())


def epic_manifests_dir() -> Path:
    base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    return base / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"


def epic_games() -> list[Game]:
    manifests = epic_manifests_dir()
    if not manifests.is_dir():
        return []
    games: dict[str, Game] = {}
    for item in manifests.glob("*.item"):
        try:
            data = json.loads(item.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("bIsIncompleteInstall"):
            continue
        if data.get("bIsApplication") is False:
            continue
        title = str(data.get("DisplayName") or "").strip()
        location = str(data.get("InstallLocation") or "").strip()
        launch = str(data.get("LaunchExecutable") or "").strip()
        app_name = str(data.get("AppName") or "").strip()
        if not title or not location or not app_name:
            continue
        if app_name in games:
            continue
        folder = Path(location)
        if not folder.is_dir():
            continue
        executable = folder / launch if launch else None
        if executable is None or not executable.is_file():
            continue
        games[app_name] = Game(
            id=slugify(f"pc-epic-{app_name}"),
            title=title,
            system="Epic Games",
            system_key="epic",
            subtitle="Epic Games",
            description=f"Juego de Epic Games instalado en {folder}.",
            executable=str(executable),
            arguments=[],
            working_dir=str(folder),
            rom_path="",
            emulator="Epic Games",
            accent=EPIC_ACCENT,
            source="epic",
            notes=f"AppName: {app_name}",
        )
    return list(games.values())


def store_games() -> list[Game]:
    return [*steam_games(), *epic_games()]
