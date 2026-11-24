from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "juego"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class Game:
    id: str
    title: str
    system: str
    system_key: str
    subtitle: str = ""
    year: int | None = None
    genre: str = ""
    description: str = ""
    executable: str = ""
    arguments: list[str] = field(default_factory=list)
    working_dir: str = ""
    rom_path: str = ""
    emulator: str = ""
    accent: str = "#E9B949"
    cover: str = ""
    favorite: bool = False
    progress: str = ""
    playtime_seconds: int = 0
    sessions: int = 0
    last_played: str = ""
    added_at: str = ""
    source: str = "auto"
    notes: str = ""
    emulator_locked: bool = False

    def __post_init__(self) -> None:
        if not self.added_at:
            self.added_at = now_iso()
        if isinstance(self.arguments, str):
            self.arguments = [self.arguments]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Game":
        known = {item.name for item in fields(cls)}
        clean = {key: value for key, value in data.items() if key in known}
        return cls(**clean)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def playtime_text(self) -> str:
        seconds = int(self.playtime_seconds)
        if seconds <= 0:
            return "Sin sesiones"
        if seconds < 60:
            return "Menos de 1 min"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} min"
        hours, remainder = divmod(minutes, 60)
        if remainder == 0:
            return f"{hours} h"
        return f"{hours} h {remainder} min"

    @property
    def last_played_text(self) -> str:
        if not self.last_played:
            return "Nunca jugado"
        try:
            moment = datetime.fromisoformat(self.last_played)
        except ValueError:
            return "Nunca jugado"
        now = datetime.now(moment.tzinfo) if moment.tzinfo else datetime.now()
        delta = now - moment
        days = delta.days
        if days <= 0:
            hours = delta.seconds // 3600
            if hours <= 0:
                return "Hace un momento"
            if hours == 1:
                return "Hace 1 hora"
            return f"Hace {hours} horas"
        if days == 1:
            return "Ayer"
        if days < 7:
            return f"Hace {days} días"
        return moment.strftime("%d/%m/%Y")

    def resolved_arguments(self) -> list[str]:
        arguments = [arg.replace("{rom}", self.rom_path or "") for arg in self.arguments]
        already_included = any(
            "{rom}" in arg or (self.rom_path and self.rom_path in arg)
            for arg in self.arguments
        )
        if (
            self.rom_path
            and self.system_key not in {"pc", "ports", "steam", "epic", "gog"}
            and not already_included
        ):
            arguments.append(self.rom_path)
        return arguments

    @property
    def command_preview(self) -> str:
        parts: list[str] = []
        for arg in self.resolved_arguments():
            value = arg
            if " " in value and not (value.startswith('"') and value.endswith('"')):
                value = f'"{value}"'
            parts.append(value)
        executable = self.executable
        if " " in executable:
            executable = f'"{executable}"'
        return " ".join([executable, *parts]).strip()

    @property
    def state(self) -> str:
        if self.progress == "finished":
            return "finished"
        if self.progress == "playing":
            return "playing"
        if self.playtime_seconds > 0 or self.sessions > 0:
            return "playing"
        return "unplayed"

    def touch_play(self, seconds: int) -> None:
        self.playtime_seconds += max(1, int(seconds))
        self.sessions += 1
        self.last_played = now_iso()
        if self.progress == "finished":
            self.progress = "playing"


@dataclass
class Emulator:
    key: str
    name: str
    executable: str = ""
    system: str = ""
    system_key: str = ""
    found: bool = False
    version: str = ""
    note: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Emulator":
        known = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in known})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
