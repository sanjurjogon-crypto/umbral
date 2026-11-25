from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .detect import _default_roots, _unique_roots
from .index import composite
from .models import Emulator, Game
from .paths import path_key as _path_key

_GENERIC_EXE_STEMS = {
    "game",
    "start",
    "launcher",
    "main",
    "play",
    "client",
    "app",
    "application",
    "bin",
    "win64",
    "win32",
    "binaries",
}


def _is_executable_valid(path_str: str) -> bool:
    if not path_str:
        return False
    target = Path(path_str)
    return target.is_file() or (target.suffix.lower() == ".app" and target.is_dir())


def is_installed(game: Game, detected_ids: set[str] | None = None) -> bool:
    """Return True if a library entry still points to an installed game on disk."""
    if game.source == "steam":
        if not _is_executable_valid(game.executable):
            return False
        if game.working_dir and not Path(game.working_dir).is_dir():
            return False
        if detected_ids is not None and game.id not in detected_ids:
            return False
        return True
    if game.rom_path:
        return Path(game.rom_path).exists()
    if not _is_executable_valid(game.executable):
        return False
    if game.source in {"epic", "gog"} and game.working_dir and not Path(game.working_dir).is_dir():
        return False
    return True


def _pick_relocated_target(
    original: Path,
    candidates: list[Path],
    *,
    require_parent_if_generic: bool = False,
) -> Path | None:
    if not candidates:
        return None
    orig_parent = original.parent.name.lower()
    parent_matches = [item for item in candidates if item.parent.name.lower() == orig_parent]
    if len(parent_matches) == 1:
        return parent_matches[0]
    if require_parent_if_generic and original.stem.lower() in _GENERIC_EXE_STEMS:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return None


def relocate_missing_paths(
    games: list[Game],
    emulators: Iterable[Emulator] | None = None,
    scan_folders: Iterable[str] | None = None,
) -> int:
    """Refresh moved ROM, standalone executable, and emulator paths across existing games.

    Returns the number of games whose paths or stale metadata were updated.
    """
    needs_index = any(
        (game.rom_path and not Path(game.rom_path).exists())
        or (
            not game.rom_path
            and game.system_key in {"pc", "ports"}
            and bool(game.executable)
            and not _is_executable_valid(game.executable)
        )
        for game in games
    )

    files_by_name: dict[str, list[Path]] = {}
    dirs_by_name: dict[str, list[Path]] = {}
    if needs_index:
        roots = _default_roots()
        for folder in scan_folders or []:
            if folder:
                path = Path(folder)
                if path.exists():
                    roots.append(path)
        media_index = composite(_unique_roots(roots))
        for entry in media_index.files:
            files_by_name.setdefault(entry.path.name.lower(), []).append(entry.path)
        for entry in media_index.dirs:
            dirs_by_name.setdefault(entry.path.name.lower(), []).append(entry.path)

    valid_emus = [emu for emu in (emulators or ()) if emu.found and _is_executable_valid(emu.executable)]
    emu_by_name = {emu.name.strip().lower(): emu for emu in valid_emus if emu.name}
    emu_by_system: dict[str, Emulator] = {}
    for emu in valid_emus:
        if emu.system_key and emu.system_key not in emu_by_system:
            emu_by_system[emu.system_key] = emu

    updated = 0
    for game in games:
        changed = False
        if game.rom_path and not Path(game.rom_path).exists():
            old_rom = Path(game.rom_path)
            key = old_rom.name.lower()
            pool = files_by_name.get(key, []) if old_rom.suffix else (dirs_by_name.get(key, []) or files_by_name.get(key, []))
            found_rom = _pick_relocated_target(old_rom, pool)
            if found_rom is not None and _path_key(str(found_rom)) != _path_key(game.rom_path):
                game.rom_path = str(found_rom)
                changed = True

        if (
            not game.rom_path
            and game.system_key in {"pc", "ports"}
            and game.executable
            and not _is_executable_valid(game.executable)
        ):
            old_exe = Path(game.executable)
            found_exe = _pick_relocated_target(
                old_exe,
                files_by_name.get(old_exe.name.lower(), []),
                require_parent_if_generic=True,
            )
            if found_exe is not None and _path_key(str(found_exe)) != _path_key(game.executable):
                game.executable = str(found_exe)
                game.working_dir = str(found_exe.parent)
                changed = True

        if game.rom_path and valid_emus:
            exe_missing = not _is_executable_valid(game.executable)
            candidate_emu = emu_by_name.get((game.emulator or "").strip().lower())
            if candidate_emu is None and exe_missing and not game.emulator_locked:
                candidate_emu = emu_by_system.get(game.system_key)
            if candidate_emu is not None and (exe_missing or not game.emulator_locked):
                if _path_key(candidate_emu.executable) != _path_key(game.executable):
                    game.executable = candidate_emu.executable
                    game.emulator = candidate_emu.name
                    if not game.working_dir or not Path(game.working_dir).is_dir():
                        game.working_dir = str(Path(candidate_emu.executable).parent)
                    changed = True

        if (
            game.source not in {"steam", "epic", "gog"}
            and _is_executable_valid(game.executable)
            and game.working_dir
            and not Path(game.working_dir).is_dir()
        ):
            game.working_dir = str(Path(game.executable).parent)
            changed = True

        if game.cover and not Path(game.cover).is_file():
            game.cover = ""
            changed = True

        if changed:
            updated += 1
    return updated


def missing_parts(game: Game) -> list[str]:
    parts: list[str] = []
    if game.rom_path and not Path(game.rom_path).exists():
        parts.append("rom")
    if not _is_executable_valid(game.executable):
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
