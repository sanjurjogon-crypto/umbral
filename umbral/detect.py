from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .index import FileIndex, composite
from .models import Emulator, Game, slugify
from .profiles import PROFILE_BY_KEY, PROFILES, EmulatorProfile
from .rom_rules import AMBIGUOUS_EXTENSIONS, rom_system, validate_rom
from .stores import store_games

DETECTION_VERSION = 6


@dataclass
class Detection:
    games: list[Game] = field(default_factory=list)
    emulators: list[Emulator] = field(default_factory=list)
    roms: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


def _default_roots() -> list[Path]:
    home = Path.home()
    return [
        home / "Games",
        home / "Downloads",
        home / "Desktop",
        home / "Documents",
    ]


def _unique_roots(roots: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _find_named(index: FileIndex, names: list[str], max_depth: int = 6, limit: int = 40) -> list[Path]:
    wanted = {name.lower() for name in names}
    found: list[Path] = []
    seen: set[str] = set()
    for entry in index.files:
        if entry.depth > max_depth:
            continue
        candidate = entry.path
        if candidate.name.lower() not in wanted:
            continue
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(candidate)
        if len(found) >= limit:
            return found
    return found


def _version_key(path: Path) -> tuple[int, ...]:
    text = " ".join(path.parts[-5:])
    numbers = re.findall(r"\d+(?:\.\d+)*", text)
    parsed: list[int] = []
    for number in numbers:
        for part in number.split("."):
            try:
                parsed.append(int(part))
            except ValueError:
                pass
    return tuple(parsed) if parsed else (0,)


def _version_text(path: Path) -> str:
    match = re.search(r"(\d+\.\d+(?:\.\d+)*)", " ".join(path.parts[-5:]))
    return match.group(1) if match else ""


def _override(paths: dict[str, str], key: str) -> Path | None:
    value = paths.get(key, "")
    return Path(value) if value else None


def _candidate_score(path: Path) -> tuple[tuple[int, ...], int]:
    parts = [part.lower() for part in path.parts]
    bonus = 0
    if "games" in parts:
        bonus += 5
    if "localappdata" in parts:
        bonus += 4
    if "program files" in parts or "program files (x86)" in parts:
        bonus += 6
    if "downloads" in parts:
        bonus += 1
    return (_version_key(path), bonus)


def _make_emulator(profile: EmulatorProfile, executable: Path, note: str = "") -> Emulator:
    return Emulator(
        profile.key,
        profile.name,
        str(executable),
        profile.system,
        profile.system_key,
        True,
        _version_text(executable),
        note,
    )


def _detect_profile(profile: EmulatorProfile, overrides: dict[str, str], candidates: list[Path]) -> Emulator:
    forced = _override(overrides, profile.key)
    if forced is not None:
        if not forced.is_file():
            return Emulator(
                profile.key,
                profile.name,
                str(forced),
                profile.system,
                profile.system_key,
                False,
                note=f"La ruta configurada no existe: {forced}",
            )
        return _make_emulator(profile, forced)

    for candidate in profile.expanded_search_paths():
        if candidate.is_file() and candidate.name.lower() in profile.wanted_names:
            return _make_emulator(profile, candidate)

    matches = [path for path in candidates if path.name.lower() in profile.wanted_names]
    if matches:
        best = max(matches, key=_candidate_score)
        return _make_emulator(profile, best)

    return Emulator(
        profile.key,
        profile.name,
        "",
        profile.system,
        profile.system_key,
        False,
        note=profile.note or "No se encontró el ejecutable en las rutas habituales.",
    )


def _hookshot_root(path: Path) -> Path:
    parent = path.parent
    if parent.name.lower() == "bin":
        candidate = parent.parent
        if (candidate / "hookshot_version.txt").exists() or (candidate / ".hookshot_romfs").exists():
            return candidate
    return parent


def _is_hookshot_builder(path: Path) -> bool:
    try:
        return path.stat().st_size < 5_000_000
    except OSError:
        return False


def _longshot_root(path: Path) -> Path:
    parent = path.parent
    if parent.name.lower() == "bin":
        return parent.parent
    return parent


def _is_longshot_stub(path: Path) -> bool:
    try:
        return path.stat().st_size < 5_000_000
    except OSError:
        return False


def detect_longshot(
    overrides: dict[str, str], index: FileIndex, candidates: list[Path] | None = None
) -> Emulator:
    profile = PROFILE_BY_KEY["longshot"]
    forced = _override(overrides, "longshot")
    if forced is not None:
        if not forced.is_file():
            return Emulator(
                "longshot",
                "Longshot",
                str(forced),
                "Ports",
                "ports",
                False,
                note=f"La ruta configurada no existe: {forced}",
            )
        return _make_emulator(profile, forced)

    found = [path for path in (candidates or []) if path.name.lower() == "longshot.exe"]
    if not found:
        found = _find_named(index, ["longshot.exe"], max_depth=8, limit=40)
    usable = [path for path in found if not _is_longshot_stub(path)]

    def score(path: Path) -> tuple[int, int]:
        parts = [part.lower() for part in path.parts]
        value = 0
        if "bin" in parts:
            value += 50
        if "stable" in parts:
            value += 20
        if "games" in parts:
            value += 5
        return (value, path.stat().st_size if path.is_file() else 0)

    if usable:
        best = max(usable, key=score)
        return _make_emulator(profile, best, "")

    if found:
        return Emulator(
            "longshot",
            "Longshot",
            "",
            "Ports",
            "ports",
            False,
            note="Solo se encontró el instalador de Longshot. Compila el juego desde su launcher.",
        )

    return Emulator(
        "longshot",
        "Longshot",
        "",
        "Ports",
        "ports",
        False,
        note="No se encontró longshot.exe. Compila el juego desde Longshot Launcher.",
    )


def detect_hookshot(
    overrides: dict[str, str], index: FileIndex, candidates: list[Path] | None = None
) -> Emulator:
    forced = _override(overrides, "hookshot")
    if forced is not None:
        if not forced.is_file():
            return Emulator(
                "hookshot",
                "Hookshot",
                str(forced),
                "Ports",
                "ports",
                False,
                note=f"La ruta configurada no existe: {forced}",
            )
        if _is_hookshot_builder(forced):
            return Emulator(
                "hookshot",
                "Hookshot",
                str(forced),
                "Ports",
                "ports",
                False,
                note="El archivo elegido parece el instalador de Hookshot Builder, no el juego.",
            )
        return _make_emulator(PROFILE_BY_KEY["hookshot"], forced)

    found = [path for path in (candidates or []) if path.name.lower() == "hookshot.exe"]
    if not found:
        found = _find_named(index, ["hookshot.exe"], max_depth=6, limit=20)
    usable = [path for path in found if not _is_hookshot_builder(path)]

    def score(path: Path) -> int:
        parent = path.parent
        parts = [part.lower() for part in path.parts]
        value = 0
        if parent.name.lower() == "bin" and (parent.parent / "hookshot_version.txt").exists():
            value += 100
        if (parent / "hookshot_version.txt").exists():
            value += 60
        if (parent / ".hookshot_romfs").exists():
            value += 20
        if (parent / "romfs").exists():
            value += 8
        if "games" in parts:
            value += 5
        if "builder" in parts:
            value -= 50
        return value

    if usable:
        best = max(usable, key=score)
        root = _hookshot_root(best)
        return _make_emulator(PROFILE_BY_KEY["hookshot"], best, _hookshot_version(root))

    if found:
        return Emulator(
            "hookshot",
            "Hookshot",
            "",
            "Ports",
            "ports",
            False,
            note="Solo se encontró el instalador de Hookshot Builder. Indica la carpeta del juego en Ajustes.",
        )

    return Emulator(
        "hookshot",
        "Hookshot",
        "",
        "Ports",
        "ports",
        False,
        note="No se encontró hookshot.exe. Indica la ruta en Ajustes.",
    )


def _hookshot_version(folder: Path) -> str:
    version_file = folder / "hookshot_version.txt"
    try:
        text = version_file.read_text(encoding="utf-8", errors="ignore").strip()
        return text.splitlines()[0][:40] if text else ""
    except OSError:
        return ""


def find_roms(index: FileIndex, extensions: tuple[str, ...], max_depth: int = 6, limit: int = 2000) -> list[Path]:
    wanted = {extension.lower() for extension in extensions}
    results: list[Path] = []
    seen: set[str] = set()
    for entry in index.files:
        if entry.depth > max_depth:
            continue
        candidate = entry.path
        if candidate.suffix.lower() not in wanted:
            continue
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(candidate)
        if len(results) >= limit:
            return results
    return results


def find_marked_folders(
    index: FileIndex, markers: tuple[str, ...], max_depth: int = 6, limit: int = 100
) -> list[tuple[Path, str]]:
    wanted = {marker.lower() for marker in markers}
    results: list[tuple[Path, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in index.dirs:
        if entry.depth > max_depth:
            continue
        name = entry.path.name.lower()
        if name not in wanted:
            continue
        folder = entry.path.parent
        key = (str(folder).lower(), name)
        if key in seen:
            continue
        seen.add(key)
        results.append((folder, name))
        if len(results) >= limit:
            return results
    return results


def clean_title(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", stem)
    stem = re.sub(r"[_.]+", " ", stem)
    stem = re.sub(r"\b(v\d+(?:\.\d+)*|rev\s*\d+|usa|eur|jpn|world|español|multi\d*)\b", " ", stem, flags=re.I)
    stem = re.sub(r"\s+", " ", stem).strip()
    if stem and stem.isupper():
        stem = stem.title()
    match = re.match(r"^(.+?),\s*(The|A|An)\s*[-:]\s*(.+)$", stem, re.I)
    if match:
        stem = f"{match.group(2).title()} {match.group(1).strip()}: {match.group(3).strip()}"
    return stem or Path(filename).stem


def _metadata(title: str, profile: EmulatorProfile, emulator: Emulator) -> dict[str, object]:
    lowered = title.lower()
    if "twilight princess" in lowered and profile.system_key == "ports":
        return {
            "title": "The Legend of Zelda: Twilight Princess",
            "subtitle": "Ports · Port nativo (Dusklight)",
            "year": 2006,
            "genre": "Acción, Aventura",
            "accent": "#8B7CD8",
            "description": (
                "La recreación nativa de Twilight Princess para PC. Usa tu propia copia del juego "
                "y arranca sin emulador desde la pantalla de inicio de Dusklight."
            ),
        }
    if "ocarina of time" in lowered:
        if profile.system_key == "ports":
            return {
                "title": "The Legend of Zelda: Ocarina of Time",
                "subtitle": f"Ports · Port nativo ({profile.name})",
                "year": 2026,
                "genre": "Aventura",
                "accent": "#E9B949",
                "description": (
                    "El remake de Ocarina of Time reconstruido para PC. Arranca desde tu propia copia, "
                    "sin emulador, con resolución alta y generación de fotogramas."
                ),
            }
        if profile.system_key == "switch2":
            return {
                "title": "The Legend of Zelda: Ocarina of Time",
                "subtitle": "Switch 2 · Emulado con Fritchii",
                "year": 2026,
                "genre": "Aventura",
                "accent": "#6EA8FE",
                "description": (
                    "El clásico de Nintendo 64 vuelto a imaginar para Switch 2. Se ejecuta con tu emulador "
                    "Fritchii y tus propios archivos del juego."
                ),
            }
    return {
        "title": title,
        "subtitle": f"{profile.system} · {profile.name}",
        "year": None,
        "genre": "",
        "accent": profile.accent,
        "description": profile.description or f"Juego de {profile.system} lanzado con {profile.name}.",
    }


def _working_dir(profile: EmulatorProfile, executable: str) -> Path:
    path = Path(executable)
    if profile.working_dir == "hookshot_root":
        return _hookshot_root(path)
    return path.parent


def _game_from_rom(rom: Path, emulator: Emulator, profile: EmulatorProfile) -> Game:
    title = clean_title(rom.name)
    metadata = _metadata(title, profile, emulator)
    return Game(
        id=slugify(f"{profile.system_key}-{metadata['title']}-{emulator.name}"),
        title=str(metadata["title"]),
        system=profile.system,
        system_key=profile.system_key,
        subtitle=str(metadata["subtitle"]),
        year=metadata["year"] if isinstance(metadata["year"], int) else None,
        genre=str(metadata["genre"]),
        description=str(metadata["description"]),
        executable=emulator.executable,
        arguments=list(profile.arguments),
        working_dir=str(_working_dir(profile, emulator.executable)),
        rom_path=str(rom),
        emulator=emulator.name,
        accent=str(metadata["accent"]),
        source="auto",
    )


def _game_from_folder(folder: Path, emulator: Emulator, profile: EmulatorProfile) -> Game:
    title = clean_title(folder.name)
    metadata = _metadata(title, profile, emulator)
    return Game(
        id=slugify(f"{profile.system_key}-{metadata['title']}-{emulator.name}"),
        title=str(metadata["title"]),
        system=profile.system,
        system_key=profile.system_key,
        subtitle=str(metadata["subtitle"]),
        year=metadata["year"] if isinstance(metadata["year"], int) else None,
        genre=str(metadata["genre"]),
        description=str(metadata["description"]),
        executable=emulator.executable,
        arguments=list(profile.arguments),
        working_dir=str(_working_dir(profile, emulator.executable)),
        rom_path=str(folder),
        emulator=emulator.name,
        accent=str(metadata["accent"]),
        source="auto",
    )


def _hookshot_game(emulator: Emulator) -> Game:
    profile = PROFILE_BY_KEY["hookshot"]
    metadata = _metadata("Ocarina of Time", profile, emulator)
    return Game(
        id=slugify("ports-ocarina-of-time-hookshot"),
        title=str(metadata["title"]),
        system="Ports",
        system_key="ports",
        subtitle=str(metadata["subtitle"]),
        year=metadata["year"] if isinstance(metadata["year"], int) else None,
        genre=str(metadata["genre"]),
        description=str(metadata["description"]),
        executable=emulator.executable,
        arguments=[],
        working_dir=str(_working_dir(profile, emulator.executable)),
        rom_path="",
        emulator=emulator.name,
        accent=str(metadata["accent"]),
        source="auto",
    )


def _longshot_game(emulator: Emulator) -> Game:
    profile = PROFILE_BY_KEY["longshot"]
    metadata = _metadata("Ocarina of Time", profile, emulator)
    return Game(
        id=slugify("ports-ocarina-of-time-longshot"),
        title=str(metadata["title"]),
        system="Ports",
        system_key="ports",
        subtitle=str(metadata["subtitle"]),
        year=metadata["year"] if isinstance(metadata["year"], int) else None,
        genre=str(metadata["genre"]),
        description=str(metadata["description"]),
        executable=emulator.executable,
        arguments=list(profile.arguments),
        working_dir=str(_working_dir(profile, emulator.executable)),
        rom_path="",
        emulator=emulator.name,
        accent=str(metadata["accent"]),
        source="auto",
    )


def _dusklight_game(emulator: Emulator) -> Game:
    profile = PROFILE_BY_KEY["dusklight"]
    metadata = _metadata("Twilight Princess", profile, emulator)
    return Game(
        id=slugify("ports-the-legend-of-zelda-twilight-princess-dusklight"),
        title=str(metadata["title"]),
        system="Ports",
        system_key="ports",
        subtitle=str(metadata["subtitle"]),
        year=metadata["year"] if isinstance(metadata["year"], int) else None,
        genre=str(metadata["genre"]),
        description=str(metadata["description"]),
        executable=emulator.executable,
        arguments=[],
        working_dir=str(_working_dir(profile, emulator.executable)),
        rom_path="",
        emulator=emulator.name,
        accent=str(metadata["accent"]),
        source="auto",
    )


def profile_for_rom(path: Path, profiles: list[EmulatorProfile]) -> EmulatorProfile | None:
    return _profile_for_rom(path, profiles)


def working_dir_for(profile: EmulatorProfile, executable: str) -> Path:
    return _working_dir(profile, executable)


def _profile_for_rom(path: Path, profiles: list[EmulatorProfile]) -> EmulatorProfile | None:
    suffix = path.suffix.lower()
    candidates = [profile for profile in profiles if suffix in profile.rom_extensions]
    if not candidates:
        return None
    if suffix in AMBIGUOUS_EXTENSIONS:
        system_key = rom_system(path)
        if system_key is None or not validate_rom(path, system_key):
            return None
        exact = [
            profile
            for profile in candidates
            if profile.system_key == system_key or system_key in profile.systems
        ]
        if not exact:
            return None
        return min(exact, key=lambda profile: (profile.priority, profile.name))
    return min(candidates, key=lambda profile: (profile.priority, profile.name))


def detect(
    emulator_paths: dict[str, str] | None = None,
    scan_folders: list[str] | None = None,
    extra_profiles: list[EmulatorProfile] | None = None,
) -> Detection:
    overrides = dict(emulator_paths or {})
    profiles = [*PROFILES, *(extra_profiles or [])]
    for profile in extra_profiles or []:
        if profile.note and profile.key not in overrides:
            overrides[profile.key] = profile.note
    roots = _default_roots()
    for folder in scan_folders or []:
        path = Path(folder)
        if path.exists():
            roots.append(path)
    unique_roots = _unique_roots(roots)
    local_env = os.environ.get("LOCALAPPDATA", "").strip()
    extra_emu_roots = [*unique_roots, Path(local_env) / "Programs"] if local_env else unique_roots
    emulator_roots = _unique_roots(extra_emu_roots)

    exe_index = composite(emulator_roots)
    media_index = composite(unique_roots)

    all_names = sorted({name for profile in profiles for name in profile.exe_names})
    candidates = _find_named(exe_index, all_names, max_depth=6, limit=300)

    found_emulators: list[Emulator] = []
    diagnostics: list[str] = []
    for profile in sorted(profiles, key=lambda item: (item.priority, item.name)):
        if profile.key == "hookshot":
            emulator = detect_hookshot(overrides, exe_index, candidates)
        elif profile.key == "longshot":
            emulator = detect_longshot(overrides, exe_index, candidates)
        else:
            emulator = _detect_profile(profile, overrides, candidates)
        if emulator.found:
            found_emulators.append(emulator)
            diagnostics.append(f"Emulador {emulator.name}: {emulator.executable}")
        else:
            detail = f" ({emulator.note})" if emulator.note else ""
            diagnostics.append(f"Emulador no encontrado: {emulator.name}{detail}")

    found_keys = {emulator.key for emulator in found_emulators}
    auto_profiles = [profile for profile in profiles if profile.auto_scan and profile.key in found_keys]
    extensions = sorted({extension for profile in auto_profiles for extension in profile.rom_extensions})
    roms = find_roms(media_index, tuple(extensions)) if extensions else []

    games: list[Game] = []
    seen_roms: set[str] = set()
    rom_paths: set[str] = set()

    for rom in roms:
        profile = _profile_for_rom(rom, auto_profiles)
        if profile is None:
            diagnostics.append(f"Descartado: {rom} (no parece una ROM válida)")
            continue
        key = str(rom).lower()
        if key in seen_roms:
            continue
        seen_roms.add(key)
        emulator = next(item for item in found_emulators if item.key == profile.key)
        games.append(_game_from_rom(rom, emulator, profile))
        rom_paths.add(str(rom))
        diagnostics.append(f"Juego {profile.name}: {rom}")

    all_markers = tuple(
        sorted({marker for profile in auto_profiles for marker in profile.folder_markers})
    )
    marked = find_marked_folders(media_index, all_markers) if all_markers else []
    for profile in auto_profiles:
        wanted_markers = {marker.lower() for marker in profile.folder_markers}
        if not wanted_markers:
            continue
        for folder, marker in marked:
            if marker not in wanted_markers:
                continue
            key = str(folder).lower()
            if key in seen_roms:
                continue
            seen_roms.add(key)
            emulator = next(item for item in found_emulators if item.key == profile.key)
            games.append(_game_from_folder(folder, emulator, profile))
            rom_paths.add(str(folder))

    longshot = next((item for item in found_emulators if item.key == "longshot"), None)
    if longshot is not None:
        games.append(_longshot_game(longshot))

    hookshot = next((item for item in found_emulators if item.key == "hookshot"), None)
    if hookshot is not None:
        games.append(_hookshot_game(hookshot))

    dusklight = next((item for item in found_emulators if item.key == "dusklight"), None)
    if dusklight is not None:
        games.append(_dusklight_game(dusklight))

    games.extend(store_games(scan_folders))
    diagnostics.append(
        f"Tiendas: {sum(1 for game in games if game.source in {'steam', 'epic', 'gog'})} juegos de Steam, Epic y GOG."
    )

    deduplicated: dict[str, Game] = {}
    for game in games:
        existing = deduplicated.get(game.id)
        if existing is None:
            deduplicated[game.id] = game
            continue
        if (
            game.rom_path
            and existing.rom_path
            and os.path.normcase(game.rom_path) != os.path.normcase(existing.rom_path)
        ):
            digest = hashlib.sha1(os.path.normcase(game.rom_path).encode("utf-8")).hexdigest()[:6]
            rom_stem = Path(game.rom_path).stem
            game.id = f"{game.id}-{digest}"
            if rom_stem and rom_stem.lower() != game.title.lower():
                game.title = rom_stem
            deduplicated.setdefault(game.id, game)

    return Detection(
        games=sorted(deduplicated.values(), key=lambda item: item.title.lower()),
        emulators=found_emulators,
        roms=sorted(rom_paths),
        diagnostics=diagnostics,
    )
