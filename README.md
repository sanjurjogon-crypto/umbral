# Umbral

Personal game library and launcher for Windows (built with Python and PySide6). Umbral unifies PC games from Steam, Epic Games, GOG, standalone executables, native ports, and emulated console ROMs into a single 3D shelf and card interface with automatic box art, playtime tracking, health diagnostics, and verified auto-updates.

---

## Features

- **Unified Library & 3D Shelf View**: Browse your collection on a keyboard- and mouse-driven 3D shelf (*Biblioteca*) or curated home shelves (*Inicio*: *Recientes*, *En curso*, *Sin jugar*, *Terminados*, *Favoritos*, *Añadidos recientes*).
- **PC Store Integration**: Automatically detects installed games from:
  - **Steam** (`libraryfolders.vdf` & `appmanifest_*.acf` across all Steam libraries)
  - **Epic Games** (`%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests\*.item`)
  - **GOG** (Windows registry entries & `goggame-*.info` manifests)
- **Emulator & Port Auto-Detection**: Built-in profiles for 35+ systems and emulators (RPCS3, Dolphin, PCSX2, DuckStation, PPSSPP, Cemu, Azahar, Lime3DS, Ryujinx, Eden, Sudachi, Yuzu, melonDS, DeSmuME, mGBA, VBA-M, MAME, FinalBurn Neo, Snes9x, FCEUX, RMG, simple64, Flycast, Kega Fusion, Mednafen, Ares, VICE, FS-UAE, openMSX, Stella, xemu, Xenia, Vita3K, RetroArch, Longshot, Hookshot, Dusklight, Ship of Harkinian, Fritchii), plus **Custom Emulators** (*Añadir emulador propio*).
- **Standalone PC Game & Download Scanner** (*Buscar juegos*): Scans folders for standalone `.exe` titles, identifies game engines (Unity, Unreal, Godot, Steam, GOG, Epic), verifies titles online via Steam, itch.io, and PCGamingWiki, and detects recent/in-progress ROM downloads.
- **Automatic Cover Art & Custom Covers**: Fetches covers from Steam CDN, LizardByte GameDB (IGDB), and itch.io with local caching. You can also assign a custom local cover image (PNG, JPEG, WebP, BMP) or clear a cover to re-fetch it from **Edit game** (*Editar ficha* → *Más opciones*).
- **Playtime, Progress & Context Actions**:
  - Tracks session count and playtime (using Windows Job Objects to track child processes spawned by launchers), prevents duplicate concurrent launches, and persists elapsed time even if Umbral is closed while a game is running.
  - Supports manual playtime editing, progress states (*Automático*, *En curso*, *Terminado*), favorites, and personal notes.
  - Right-click context menu on cards and 3D shelf items for quick launch, favorite/finished toggles, editing, folder access, and removal.
- **Library Health & Path Relinking** (*Salud*): Flags missing executables, missing ROM paths, and missing emulator firmware (such as RPCS3 `dev_flash`), and lets you relink (*Reasignar*) moved files directly.
- **Library Export & Import**: Back up your entire library (games, playtime, sessions, favorites, progress, notes, and settings) to a JSON file and merge/import it on another installation via **Settings** (*Ajustes* → *Datos y mantenimiento* → *Exportar biblioteca* / *Importar biblioteca*).
- **Verified Self-Updater**: Checks GitHub Releases for newer versions of `Umbral.exe`, verifies download size, PE header, and SHA-256 digest/checksum, creates a data backup, and swaps the binary safely.

---

## Installation

### Option 1: Pre-built Windows Executable

1. Download the latest `Umbral.exe` from [GitHub Releases](https://github.com/sanjurjogon-crypto/umbral/releases/latest).
2. Place `Umbral.exe` in a writable folder (e.g., `Downloads` or `C:\Games\Umbral`). Avoid OneDrive-synced folders.
3. Launch `Umbral.exe`. If Windows SmartScreen warns about an unsigned binary, click **More info** → **Run anyway**.

### Option 2: Run from Source

**Prerequisites**: Python 3.12+ (3.12 and 3.13 verified).

```bash
git clone https://github.com/sanjurjogon-crypto/umbral.git
cd umbral
python -m venv .venv
```

Activate the virtual environment and install dependencies:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
```

Launch Umbral:

```bash
python main.py
```

On Windows, you can also double-click `Ejecutar Umbral.bat`.

---

## Configuration & Environment Variables

Umbral stores all persistent user data separately from the executable so updates and moves never lose your library:

| Location / File | Purpose |
| --- | --- |
| `%APPDATA%\Umbral\library.json` | Game library, playtime, sessions, favorites, notes (with `.bak1`–`.bak3` rotating backups) |
| `%APPDATA%\Umbral\settings.json` | Scan folders, emulator overrides, custom emulators, hidden items, sort preferences |
| `%APPDATA%\Umbral\covers\` | Downloaded cover art and extracted executable icon badges |
| `%APPDATA%\Umbral\cover_cache.json` | Online cover lookup cache (30-day TTL) |
| `%APPDATA%\Umbral\standalone_cache.json` | Standalone PC game online verification cache (7-day TTL) |
| `%APPDATA%\Umbral\downloads_seen.json` | Previously reviewed ROM downloads |
| `%APPDATA%\Umbral\logs\` | Per-launch output logs (automatically pruned to the 50 most recent) |
| `%APPDATA%\Umbral\backups\` | Automatic pre-update snapshots of `library.json` and `settings.json` |

### Environment Variables

| Variable | Default / Behavior | Usage |
| --- | --- | --- |
| `APPDATA` | Falls back to `~/.umbral` if unset | Base directory for Umbral's persistent data folder (`<APPDATA>/Umbral`) |
| `LOCALAPPDATA` | Optional; falls back to system temp for updates | Used for staging self-updates (`<LOCALAPPDATA>/Umbral/update`) and scanning `%LOCALAPPDATA%\Programs` for emulators |
| `PROGRAMDATA` | `C:\ProgramData` | Used to locate Epic Games Launcher manifests (`<PROGRAMDATA>/Epic/EpicGamesLauncher/Data/Manifests`) |
| `QT_QPA_PLATFORM` | System default | Set to `offscreen` when running tests in headless or CI environments |

---

## Usage Guide

### Keyboard Shortcuts

- `←` / `→` or `A` / `D`: Move between games in the 3D shelf
- `Home` / `End`: Jump to the first or last game in the shelf
- `PageUp` / `PageDown`: Skip 5 games backward or forward
- `Enter` / `Space`: Launch the selected game
- `I` / `↑`: Open the selected game's detail sheet (*Ver ficha*)
- `Ctrl+F`: Focus the library search bar (matches title, subtitle, genre, system, emulator, year, and notes)
- `Ctrl+R`: Re-run emulator, store, and ROM detection

### Adding Games & Custom Emulators

- **Add a single game** (*＋ Añadir juego*): Select a ROM, folder, or `.exe`. Umbral auto-detects the system and installed emulator. Expand **More options** (*Más opciones*) to configure launch arguments (`{rom}` placeholder), working directory, custom cover image, progress state, manual playtime (minutes), accent color, and personal notes.
- **Scan for PC & Store games** (*Buscar juegos*): Scans default user folders (`Games`, `Downloads`, `Desktop`, `Documents`) plus any custom folders configured in **Settings** (*Ajustes* → *Carpetas escaneadas*), as well as Steam, Epic Games, and GOG.
- **Custom emulators** (*Ajustes* → *Añadir o detectar emulador* → *Añadir emulador propio*): Register any emulator executable, target console, launch arguments, and ROM file extensions.

### Exporting & Importing Your Library

1. Open **Settings** (*Ajustes*) and scroll to **Data & maintenance** (*Datos y mantenimiento*).
2. Click **Export library** (*Exportar biblioteca*) to save a portable `.json` snapshot of your games, playtime, favorites, notes, and settings.
3. Click **Import library** (*Importar biblioteca*) to merge a backup into your current library—existing games preserve the higher playtime/session count and merge missing metadata without overwriting local paths.

---

## Development & Testing

Install development dependencies and run the test suite:

```bash
pip install -r requirements.txt -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest
```

### Building the Windows Executable

```powershell
python -m PyInstaller --noconfirm Umbral.spec
```

The compiled binary is written to `dist\Umbral.exe`. Maintainers can also use `tools/release.ps1` to build, generate `Umbral.exe.sha256`, tag, and publish a GitHub Release.
