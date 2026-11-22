from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import Game
from .paths import library_file, settings_file
from .rom_rules import is_ambiguous, plausible

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
}


def _read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


class Store:
    def __init__(self) -> None:
        loaded = _read_json(settings_file(), {})
        self.settings: dict[str, Any] = {**DEFAULT_SETTINGS, **loaded}
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
        raw = _read_json(library_file(), {"games": []})
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
        kept: list[Game] = []
        removed = 0
        for game in self.games:
            if (
                game.source == "auto"
                and game.rom_path
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
        keys = {os.path.normcase(str(value)) for value in (game.executable, game.rom_path) if value}
        if paths and keys.intersection(paths):
            self.settings["hidden_paths"] = [item for item in paths if item not in keys]
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

    def hide(self, game_id: str) -> None:
        game = self.get(game_id)
        self.remove(game_id)
        hidden = self.settings.setdefault("hidden_games", [])
        if game_id not in hidden:
            hidden.append(game_id)
        if game is not None:
            paths = self.settings.setdefault("hidden_paths", [])
            for value in (game.executable, game.rom_path):
                if not value:
                    continue
                key = os.path.normcase(str(value))
                if key not in paths:
                    paths.append(key)
        self.save_settings()

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
        hidden_paths = {str(item) for item in self.settings.get("hidden_paths", [])}
        by_executable = {
            os.path.normcase(game.executable): game
            for game in self.games
            if game.executable and game.system_key in {"pc", "ports"}
        }
        by_rom = {
            os.path.normcase(game.rom_path): game
            for game in self.games
            if game.rom_path
        }
        for fresh in detected:
            if fresh.id in hidden:
                continue
            if os.path.normcase(fresh.executable) in hidden_paths:
                continue
            if fresh.rom_path and os.path.normcase(fresh.rom_path) in hidden_paths:
                continue
            existing = by_id.get(fresh.id)
            if existing is None:
                twin = None
                if fresh.rom_path:
                    twin = by_rom.get(os.path.normcase(fresh.rom_path))
                elif fresh.system_key in {"pc", "ports"}:
                    twin = by_executable.get(os.path.normcase(fresh.executable))
                if twin is not None:
                    twin.emulator = fresh.emulator
                    twin.arguments = list(fresh.arguments)
                    if fresh.executable:
                        twin.executable = fresh.executable
                    if fresh.working_dir:
                        twin.working_dir = fresh.working_dir
                    if fresh.system_key in {"pc", "ports"} and fresh.rom_path:
                        if not twin.description:
                            twin.description = fresh.description
                    elif twin.source != "manual":
                        if fresh.title:
                            twin.title = fresh.title
                        if fresh.subtitle:
                            twin.subtitle = fresh.subtitle
                        if fresh.accent:
                            twin.accent = fresh.accent
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
                continue
            for name in updatable:
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
