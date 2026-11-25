from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .models import Game, now_iso
from .paths import library_file, path_key as _path_key, settings_file
from .relink import is_installed
from .rom_rules import is_ambiguous, plausible

BACKUP_COUNT = 3

DEFAULT_SETTINGS: dict[str, Any] = {
    "version": 1,
    "first_run": True,
    "accent": "#C9A45F",
    "style": "souls",
    "scan_folders": [],
    "emulator_paths": {},
    "custom_emulators": [],
    "hidden_games": [],
    "hidden_paths": [],
    "detection_version": 0,
    "sound": False,
    "update_dismissed_version": "",
    "library_view": "shelf",
    "hide_demos": False,
    "shelf_halo": True,
}


def _backup_paths(path: Path) -> list[Path]:
    return [
        path.with_name(f"{path.name}.bak{index}")
        for index in range(1, BACKUP_COUNT + 1)
    ]


def _read_json(path: Path, default: Any) -> tuple[Any, Path | None]:
    if path.is_file():
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle), None
        except (OSError, ValueError):
            try:
                shutil.copy2(path, path.with_name(f"{path.name}.corrupt"))
            except OSError:
                pass
    for backup in _backup_paths(path):
        try:
            with backup.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        try:
            shutil.copy2(backup, path)
        except OSError:
            pass
        return data, backup
    return default, None


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backups = _backup_paths(path)
    if path.is_file():
        valid = True
        try:
            with path.open("r", encoding="utf-8") as handle:
                json.load(handle)
        except (OSError, ValueError):
            valid = False
        if valid:
            for index in range(len(backups) - 1, 0, -1):
                source = backups[index - 1]
                target = backups[index]
                if source.is_file():
                    try:
                        os.replace(source, target)
                    except OSError:
                        pass
            try:
                shutil.copy2(path, backups[0])
            except OSError:
                pass
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


class Store:
    def __init__(self) -> None:
        loaded, settings_backup = _read_json(settings_file(), {})
        if not isinstance(loaded, dict):
            loaded = {}
        self.settings: dict[str, Any] = {**copy.deepcopy(DEFAULT_SETTINGS), **loaded}
        self.recovery_notice = ""
        if settings_backup is not None:
            self.recovery_notice = (
                f"settings.json restaurado desde {settings_backup.name}."
            )
        if str(self.settings.get("accent", "")).upper() == "#E9B949":
            self.settings["accent"] = "#C9A45F"
        self.settings.setdefault("emulator_paths", {})
        self.settings.setdefault("custom_emulators", [])
        self.settings.setdefault("scan_folders", [])
        self.settings.setdefault("hidden_games", [])
        self.settings.setdefault("hidden_paths", [])
        self.games: list[Game] = []
        self._load_library()

    def _load_library(self) -> None:
        raw, library_backup = _read_json(library_file(), {"games": []})
        if library_backup is not None:
            note = f"library.json restaurado desde {library_backup.name}."
            self.recovery_notice = f"{self.recovery_notice} {note}".strip()
        games = raw.get("games", []) if isinstance(raw, dict) else []
        self.games = [Game.from_dict(item) for item in games if isinstance(item, dict)]
        for game in self.games:
            if game.source == "steam":
                game.system = "Steam"
                game.system_key = "steam"
                game.subtitle = "Steam"
            elif game.source == "epic":
                game.system = "Epic Games"
                game.system_key = "epic"
                game.subtitle = "Epic Games"
            elif game.source == "gog":
                game.system = "GOG"
                game.system_key = "gog"
                game.subtitle = "GOG"
            elif (
                game.source == "manual"
                and game.system_key == "otros"
                and game.executable.lower().endswith(".exe")
                and not game.rom_path
            ):
                game.system = "PC"
                game.system_key = "pc"
                game.subtitle = "PC"
        changed = False
        for game in self.games:
            if game.executable.lower().endswith("dusklight.exe") and game.emulator != "Dusklight":
                game.emulator = "Dusklight"
                changed = True
            if game.cover and not Path(game.cover).is_file():
                game.cover = ""
                changed = True
        kept: list[Game] = []
        removed = 0
        hidden = {str(item) for item in self.settings.get("hidden_games", [])}
        hidden_paths = {_path_key(str(item)) for item in self.settings.get("hidden_paths", [])}
        for game in self.games:
            if game.id in hidden:
                removed += 1
                continue
            if game.rom_path and _path_key(game.rom_path) in hidden_paths:
                removed += 1
                continue
            if (
                not game.rom_path
                and game.system_key in {"pc", "ports"}
                and game.executable
                and _path_key(game.executable) in hidden_paths
            ):
                removed += 1
                continue
            if (
                game.source == "auto"
                and game.rom_path
                and Path(game.rom_path).is_file()
                and is_ambiguous(game.rom_path)
                and not plausible(game.rom_path, game.system_key)
            ):
                removed += 1
                continue
            kept.append(game)
        if removed:
            self.games = kept
            changed = True
        if changed:
            self.save_library()

    def save_library(self) -> None:
        _write_json(library_file(), {"version": 1, "games": [game.to_dict() for game in self.games]})

    def save_settings(self) -> None:
        _write_json(settings_file(), self.settings)

    def export_library(self, destination: Path) -> Path:
        payload = {
            "version": 1,
            "app": "Umbral",
            "exported_at": now_iso(),
            "games": [game.to_dict() for game in self.games],
            "settings": dict(self.settings),
        }
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
        return target

    def import_library(self, source: Path) -> tuple[int, int]:
        path = Path(source)
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict) or not isinstance(raw.get("games"), list):
            raise ValueError("El archivo no es una copia válida de Umbral.")

        added = 0
        updated = 0
        for item in raw["games"]:
            if not isinstance(item, dict) or not item.get("id") or not item.get("title"):
                continue
            incoming = Game.from_dict(item)
            existing = self.get(incoming.id)
            if existing is None:
                self.upsert(incoming)
                added += 1
                continue
            changed = False
            if incoming.playtime_seconds > existing.playtime_seconds:
                existing.playtime_seconds = incoming.playtime_seconds
                changed = True
            if incoming.sessions > existing.sessions:
                existing.sessions = incoming.sessions
                changed = True
            if incoming.last_played and incoming.last_played > (existing.last_played or ""):
                existing.last_played = incoming.last_played
                changed = True
            if incoming.favorite and not existing.favorite:
                existing.favorite = True
                changed = True
            if incoming.progress and not existing.progress:
                existing.progress = incoming.progress
                changed = True
            for attr in ("notes", "genre", "description"):
                if getattr(incoming, attr) and not getattr(existing, attr):
                    setattr(existing, attr, getattr(incoming, attr))
                    changed = True
            if incoming.year and not existing.year:
                existing.year = incoming.year
                changed = True
            if incoming.cover and not existing.cover and Path(incoming.cover).is_file():
                existing.cover = incoming.cover
                changed = True
            if changed:
                updated += 1

        imported_settings = raw.get("settings")
        if isinstance(imported_settings, dict):
            for key in ("scan_folders", "hidden_games", "hidden_paths"):
                values = imported_settings.get(key)
                if isinstance(values, list):
                    current = self.settings.setdefault(key, [])
                    for entry in values:
                        if entry not in current:
                            current.append(entry)
            emu_paths = imported_settings.get("emulator_paths")
            if isinstance(emu_paths, dict):
                current_paths = self.settings.setdefault("emulator_paths", {})
                for key, value in emu_paths.items():
                    if key not in current_paths and value:
                        current_paths[key] = value
            custom = imported_settings.get("custom_emulators")
            if isinstance(custom, list):
                current_custom = self.settings.setdefault("custom_emulators", [])
                known_keys = {
                    str(item.get("key")) for item in current_custom if isinstance(item, dict)
                }
                for item in custom:
                    if isinstance(item, dict) and str(item.get("key")) not in known_keys:
                        current_custom.append(item)
                        known_keys.add(str(item.get("key")))

        self.save_library()
        self.save_settings()
        return added, updated

    def get(self, game_id: str) -> Game | None:
        for game in self.games:
            if game.id == game_id:
                return game
        return None

    def upsert(self, game: Game) -> None:
        hidden = self.settings.get("hidden_games", [])
        changed = False
        if hidden and game.id in hidden:
            self.settings["hidden_games"] = [item for item in hidden if item != game.id]
            changed = True
        paths = self.settings.get("hidden_paths", [])
        keys = {_path_key(str(value)) for value in self._hidden_values(game)}
        if paths and keys.intersection({_path_key(str(item)) for item in paths}):
            self.settings["hidden_paths"] = [
                item for item in paths if _path_key(str(item)) not in keys
            ]
            changed = True
        if changed:
            self.save_settings()
        for index, existing in enumerate(self.games):
            if existing.id == game.id:
                self.games[index] = game
                return
        self.games.append(game)

    def remove(self, game_id: str) -> None:
        self.games = [game for game in self.games if game.id != game_id]

    def prune_missing(self, detected_ids: set[str] | None = None) -> list[Game]:
        """Remove games whose installed files or manifests are no longer present."""
        kept: list[Game] = []
        removed: list[Game] = []
        for game in self.games:
            if is_installed(game, detected_ids=detected_ids):
                kept.append(game)
            else:
                removed.append(game)
        if removed:
            self.games = kept
        return removed

    def hide(self, game_id: str) -> None:
        game = self.get(game_id)
        self.remove(game_id)
        hidden = self.settings.setdefault("hidden_games", [])
        if game_id not in hidden:
            hidden.append(game_id)
        if game is not None:
            paths = self.settings.setdefault("hidden_paths", [])
            for value in self._hidden_values(game):
                key = _path_key(str(value))
                if key not in {_path_key(str(item)) for item in paths}:
                    paths.append(key)
        self.save_settings()

    def unhide_game(self, game_id: str) -> bool:
        hidden = self.settings.get("hidden_games", [])
        if not isinstance(hidden, list) or game_id not in hidden:
            return False
        self.settings["hidden_games"] = [item for item in hidden if item != game_id]
        self.save_settings()
        return True

    def unhide_path(self, path: str) -> bool:
        paths = self.settings.get("hidden_paths", [])
        if not isinstance(paths, list):
            return False
        target = _path_key(str(path))
        filtered = [item for item in paths if _path_key(str(item)) != target]
        if len(filtered) == len(paths):
            return False
        self.settings["hidden_paths"] = filtered
        self.save_settings()
        return True

    @staticmethod
    def _hidden_values(game: Game) -> list[str]:
        values: list[str] = []
        if game.rom_path:
            values.append(game.rom_path)
        if game.system_key in {"pc", "ports"} and game.executable:
            values.append(game.executable)
        return values

    def merge_detected(self, detected: list[Game]) -> None:
        by_id = {game.id: game for game in self.games}
        updatable = (
            "title",
            "system",
            "system_key",
            "subtitle",
            "year",
            "genre",
            "description",
            "executable",
            "arguments",
            "working_dir",
            "rom_path",
            "emulator",
            "accent",
        )
        hidden = {str(item) for item in self.settings.get("hidden_games", [])}
        hidden_paths = {_path_key(str(item)) for item in self.settings.get("hidden_paths", [])}
        by_executable = {
            _path_key(game.executable): game
            for game in self.games
            if game.executable and game.system_key in {"pc", "ports"}
        }
        by_rom = {
            _path_key(game.rom_path): game
            for game in self.games
            if game.rom_path
        }
        for fresh in detected:
            if fresh.id in hidden:
                continue
            if fresh.rom_path:
                if _path_key(fresh.rom_path) in hidden_paths:
                    continue
            elif fresh.system_key in {"pc", "ports"}:
                if _path_key(fresh.executable) in hidden_paths:
                    continue
            if (
                fresh.source == "auto"
                and fresh.rom_path
                and Path(fresh.rom_path).is_file()
                and is_ambiguous(fresh.rom_path)
                and not plausible(fresh.rom_path, fresh.system_key)
            ):
                continue
            existing = by_id.get(fresh.id)
            if existing is None:
                twin = None
                if fresh.rom_path:
                    twin = by_rom.get(_path_key(fresh.rom_path))
                if twin is None and fresh.system_key in {"pc", "ports"} and fresh.executable:
                    twin = by_executable.get(_path_key(fresh.executable))
                if twin is not None:
                    if twin.source != "manual" or not twin.arguments:
                        twin.arguments = list(fresh.arguments)
                    if fresh.emulator and (twin.source != "manual" or not twin.emulator):
                        twin.emulator = fresh.emulator
                    if fresh.executable and (twin.source != "manual" or not twin.executable):
                        twin.executable = fresh.executable
                    if fresh.working_dir and (twin.source != "manual" or not twin.working_dir):
                        twin.working_dir = fresh.working_dir
                    if fresh.system_key in {"pc", "ports"} and fresh.rom_path:
                        if not twin.rom_path:
                            twin.rom_path = fresh.rom_path
                        if not twin.description:
                            twin.description = fresh.description
                    elif twin.source != "manual":
                        if fresh.title:
                            twin.title = fresh.title
                        if fresh.subtitle:
                            twin.subtitle = fresh.subtitle
                        if fresh.accent:
                            twin.accent = fresh.accent
                        if fresh.rom_path:
                            twin.rom_path = fresh.rom_path
                        if fresh.system_key:
                            twin.system_key = fresh.system_key
                            twin.system = fresh.system
                        twin.description = fresh.description
                        twin.year = fresh.year
                        twin.genre = fresh.genre
                    else:
                        if not twin.description:
                            twin.description = fresh.description
                        if not twin.year:
                            twin.year = fresh.year
                        if not twin.genre:
                            twin.genre = fresh.genre
                    continue
                self.games.append(fresh)
                by_id[fresh.id] = fresh
                if fresh.rom_path:
                    by_rom[_path_key(fresh.rom_path)] = fresh
                elif fresh.system_key in {"pc", "ports"} and fresh.executable:
                    by_executable[_path_key(fresh.executable)] = fresh
                continue
            for name in updatable:
                if existing.source == "manual":
                    current = getattr(existing, name)
                    if name == "rom_path" and not current:
                        existing.rom_path = fresh.rom_path
                    elif name == "executable" and not current:
                        existing.executable = fresh.executable
                    elif name == "working_dir" and not current:
                        existing.working_dir = fresh.working_dir
                    elif name == "arguments" and not current:
                        existing.arguments = list(fresh.arguments)
                    elif name == "description" and not current:
                        existing.description = fresh.description
                    elif name == "emulator" and not current:
                        existing.emulator = fresh.emulator
                    continue
                setattr(existing, name, getattr(fresh, name))

    def systems(self) -> list[tuple[str, str, int]]:
        counts: dict[str, tuple[str, int]] = {}
        for game in self.games:
            label, count = counts.get(game.system_key, (game.system, 0))
            counts[game.system_key] = (label, count + 1)
        return sorted(
            ((key, label, count) for key, (label, count) in counts.items()),
            key=lambda item: (-item[2], item[1]),
        )

    def stats(self) -> dict[str, Any]:
        total_seconds = sum(game.playtime_seconds for game in self.games)
        sessions = sum(game.sessions for game in self.games)
        systems: dict[str, int] = {}
        for game in self.games:
            systems[game.system] = systems.get(game.system, 0) + game.playtime_seconds
        most_played = max(self.games, key=lambda game: game.playtime_seconds, default=None)
        last_played = max((game.last_played for game in self.games if game.last_played), default="")
        return {
            "total_seconds": total_seconds,
            "sessions": sessions,
            "games": len(self.games),
            "systems": systems,
            "most_played": most_played if most_played and most_played.playtime_seconds > 0 else None,
            "last_played": last_played,
        }


def format_seconds(seconds: int) -> str:
    seconds = int(seconds)
    if seconds <= 0:
        return "0 min"
    if seconds < 60:
        return "Menos de 1 min"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours, remainder = divmod(minutes, 60)
    if remainder == 0:
        return f"{hours} h"
    return f"{hours} h {remainder} min"
