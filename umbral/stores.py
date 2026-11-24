from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path
from typing import Iterable

from .models import Game, slugify

STEAM_ACCENT = "#66c0f4"
EPIC_ACCENT = "#c7c9cc"
GOG_ACCENT = "#a87cd8"

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
        if ":" in match.group(1)
        or match.group(1).startswith("\\\\")
        or match.group(1).startswith("/")
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
                working_dir=str(folder),
                rom_path="",
                emulator="Steam",
                accent=STEAM_ACCENT,
                source="steam",
                notes=f"AppID de Steam: {app_id}",
            )
    return list(games.values())


EPIC_SKIP_EXE = (
    "crashreport",
    "epicwebhelper",
    "uninstall",
    "_eac",
    "eac_",
    "easyanticheat",
    "bootstrap",
    "prereq",
    "dxsetup",
    "dxwebsetup",
    "vcredist",
    "oalinst",
    "epiconlineservices",
)

EPIC_SKIP_DIRS = {
    ".egstore",
    "engine",
    "content",
    "paks",
    "cloud",
    "saved",
    "config",
    "prerequisites",
    "redist",
    "directxredist",
    "gameinputredist",
}

EPIC_LAUNCH_NAMES = {
    "fortnite": ("fortnitelauncher.exe",),
    "rocketleague": ("rocketleague.exe",),
}

EPIC_TITLE_OVERRIDES = {
    "fortnite": "Fortnite",
    "rocketleague": "Rocket League",
}

EPIC_SKIP_FOLDERS = {
    "epic online services",
    "epic games launcher",
    "launcher",
    "unreal engine",
    "directxredist",
    "gameinputredist",
}


def epic_manifests_dir() -> Path:
    base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    return base / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"


def _epic_compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _epic_title(folder: Path) -> str:
    override = EPIC_TITLE_OVERRIDES.get(folder.name.lower())
    if override:
        return override
    text = re.sub(r"[_.]+", " ", folder.name)
    text = re.sub(r"\s+", " ", text).strip()
    if text.islower():
        text = text.title()
    return text or folder.name


def _epic_executable(folder: Path, title: str) -> Path | None:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(
        folder, topdown=True, onerror=lambda _error: None
    ):
        current = Path(dirpath)
        try:
            depth = len(current.relative_to(folder).parts)
        except ValueError:
            depth = 0
        if depth >= 5:
            dirnames[:] = []
        else:
            dirnames[:] = [
                name for name in dirnames if name.lower() not in EPIC_SKIP_DIRS
            ]
        for name in filenames:
            lower = name.lower()
            if not lower.endswith(".exe"):
                continue
            if any(token in lower for token in EPIC_SKIP_EXE):
                continue
            found.append(current / name)
    if not found:
        return None
    by_name = {path.name.lower(): path for path in found}
    for name in EPIC_LAUNCH_NAMES.get(folder.name.lower(), ()):
        if name in by_name:
            return by_name[name]
    for wanted in (_epic_compact(title), _epic_compact(folder.name)):
        if not wanted:
            continue
        for path in found:
            if _epic_compact(path.stem) == wanted:
                return path
    return max(found, key=lambda path: path.stat().st_size)


def epic_install_roots() -> list[Path]:
    roots: list[Path] = []
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = os.environ.get(variable)
        if not base:
            continue
        path = Path(base) / "Epic Games"
        if path.is_dir() and path not in roots:
            roots.append(path)
    return roots


def _launcher_installed_locations() -> list[Path]:
    base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    path = base / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat"
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, ValueError):
        return []
    entries = data.get("InstallationList") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    locations: list[Path] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        location = str(entry.get("InstallLocation") or "").strip()
        if location and Path(location).is_dir():
            locations.append(Path(location))
    return locations


def _is_epic_skip_name(folder: Path) -> bool:
    name = folder.name.strip().lower()
    if name in EPIC_SKIP_FOLDERS:
        return True
    return name.startswith("ue_") or name.startswith("unreal engine")


def _is_epic_game_folder(folder: Path) -> bool:
    if _is_epic_skip_name(folder):
        return False
    return (folder / ".egstore").is_dir()


def _epic_game_from_folder(folder: Path) -> Game | None:
    title = _epic_title(folder)
    executable = _epic_executable(folder, title)
    if executable is None:
        return None
    return Game(
        id=slugify(f"pc-epic-{folder.name}"),
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
        notes=f"Carpeta de Epic: {folder.name}",
    )


def epic_games(roots: list[Path] | None = None) -> list[Game]:
    games: dict[str, Game] = {}
    covered: set[str] = set()
    manifests = epic_manifests_dir()
    if manifests.is_dir():
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
            covered.add(os.path.normcase(str(folder)))
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

    for folder in _launcher_installed_locations():
        if _is_epic_skip_name(folder):
            continue
        key = os.path.normcase(str(folder))
        if key in covered:
            continue
        game = _epic_game_from_folder(folder)
        if game is not None:
            covered.add(key)
            games.setdefault(game.id, game)

    for root in roots if roots is not None else epic_install_roots():
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for folder in children:
            if not folder.is_dir():
                continue
            if not _is_epic_game_folder(folder):
                continue
            key = os.path.normcase(str(folder))
            if key in covered:
                continue
            game = _epic_game_from_folder(folder)
            if game is not None:
                covered.add(key)
                games.setdefault(game.id, game)
    return list(games.values())


def _gog_info_game(info_file: Path) -> Game | None:
    try:
        data = json.loads(info_file.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    game_id = str(data.get("gameId") or "").strip()
    title = str(data.get("name") or "").strip()
    if not game_id or not title:
        return None
    folder = info_file.parent
    tasks = data.get("playTasks") or []
    if not isinstance(tasks, list):
        return None
    chosen: dict | None = None
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if task.get("isHidden"):
            continue
        if task.get("isPrimary") and task.get("category") == "game":
            chosen = task
            break
        if chosen is None and task.get("category") == "game":
            chosen = task
        elif chosen is None and task.get("path"):
            chosen = task
    if chosen is None:
        return None
    rel_exe = str(chosen.get("path") or "").strip()
    if not rel_exe:
        return None
    exe_path = Path(rel_exe)
    if not exe_path.is_absolute():
        exe_path = folder / exe_path
    if not exe_path.is_file():
        return None
    raw_args = str(chosen.get("arguments") or "").strip()
    arguments = shlex.split(raw_args, posix=False) if raw_args else []
    rel_wd = str(chosen.get("workingDir") or "").strip()
    working_dir = (folder / rel_wd) if rel_wd and not Path(rel_wd).is_absolute() else (Path(rel_wd) if rel_wd else exe_path.parent)
    if not working_dir.is_dir():
        working_dir = exe_path.parent
    return Game(
        id=slugify(f"pc-gog-{game_id}"),
        title=title,
        system="GOG",
        system_key="gog",
        subtitle="GOG",
        description=f"Juego de GOG instalado en {folder}.",
        executable=str(exe_path),
        arguments=arguments,
        working_dir=str(working_dir),
        rom_path="",
        emulator="GOG",
        accent=GOG_ACCENT,
        source="gog",
        notes=f"GOG ID: {game_id}",
    )


def _gog_registry_games() -> list[Game]:
    try:
        import winreg
    except ImportError:
        return []
    games: list[Game] = []
    registry_roots = (
        r"SOFTWARE\WOW6432Node\GOG.com\Games",
        r"SOFTWARE\GOG.com\Games",
    )
    for subkey in registry_roots:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey) as root:
                index = 0
                while True:
                    try:
                        game_id = winreg.EnumKey(root, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(root, game_id) as handle:
                            def _val(name: str) -> str:
                                try:
                                    value, _ = winreg.QueryValueEx(handle, name)
                                    return str(value or "").strip()
                                except OSError:
                                    return ""

                            title = _val("gameName")
                            exe = _val("exe")
                            folder = _val("path")
                            working_dir = _val("workingDir")
                            launch_param = _val("launchParam")
                    except OSError:
                        continue
                    if not title or not exe or not Path(exe).is_file():
                        continue
                    wd = Path(working_dir) if working_dir and Path(working_dir).is_dir() else Path(exe).parent
                    games.append(
                        Game(
                            id=slugify(f"pc-gog-{game_id}"),
                            title=title,
                            system="GOG",
                            system_key="gog",
                            subtitle="GOG",
                            description=f"Juego de GOG instalado en {folder or wd}.",
                            executable=exe,
                            arguments=shlex.split(launch_param, posix=False) if launch_param else [],
                            working_dir=str(wd),
                            rom_path="",
                            emulator="GOG",
                            accent=GOG_ACCENT,
                            source="gog",
                            notes=f"GOG ID: {game_id}",
                        )
                    )
        except OSError:
            continue
    return games


def gog_roots(scan_folders: Iterable[str] | None = None) -> list[Path]:
    candidates = [
        Path(r"C:\GOG Games"),
        Path(r"C:\Program Files (x86)\GOG Galaxy\Games"),
        Path(r"C:\Program Files\GOG Galaxy\Games"),
    ]
    for folder in scan_folders or []:
        if folder:
            candidates.append(Path(folder))
    unique: list[Path] = []
    seen: set[str] = set()
    for root in candidates:
        key = os.path.normcase(str(root))
        if key in seen or not root.is_dir():
            continue
        seen.add(key)
        unique.append(root)
    return unique


def gog_games(scan_folders: Iterable[str] | None = None) -> list[Game]:
    games: dict[str, Game] = {}
    for game in _gog_registry_games():
        games.setdefault(game.id, game)
    for root in gog_roots(scan_folders):
        base_parts = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=lambda _e: None):
            depth = len(Path(dirpath).parts) - base_parts
            if depth >= 3:
                dirnames[:] = []
            for filename in filenames:
                if filename.lower().startswith("goggame-") and filename.lower().endswith(".info"):
                    game = _gog_info_game(Path(dirpath) / filename)
                    if game is not None and game.id not in games:
                        games[game.id] = game
    return list(games.values())


def store_games(scan_folders: Iterable[str] | None = None) -> list[Game]:
    return [*steam_games(), *epic_games(), *gog_games(scan_folders)]
