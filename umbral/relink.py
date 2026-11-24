from __future__ import annotations

from pathlib import Path

from .models import Game


def missing_parts(game: Game) -> list[str]:
    parts: list[str] = []
    if game.rom_path and not Path(game.rom_path).exists():
        parts.append("rom")
    if not game.executable or not Path(game.executable).is_file():
        parts.append("executable")
    return parts


def relink(game: Game, part: str, path: str | Path) -> bool:
    target = Path(path)
    if part == "executable":
        if not target.is_file():
            return False
        game.executable = str(target)
        if not game.working_dir or not Path(game.working_dir).is_dir():
            game.working_dir = str(target.parent)
        return True
    if part == "rom":
        if not target.exists():
            return False
        game.rom_path = str(target)
        return True
    return False
