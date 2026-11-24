from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .consoles import SYSTEM_LABELS


@dataclass(frozen=True)
class EmulatorProfile:
    key: str
    name: str
    system: str
    system_key: str
    exe_names: tuple[str, ...]
    arguments: tuple[str, ...] = ("{rom}",)
    rom_extensions: tuple[str, ...] = ()
    systems: tuple[str, ...] = ()
    folder_markers: tuple[str, ...] = ()
    search_paths: tuple[str, ...] = ()
    flatpak_ids: tuple[str, ...] = ()
    working_dir: str = "exe_parent"
    priority: int = 50
    auto_scan: bool = True
    accent: str = "#E9B949"
    description: str = ""
    note: str = ""
    firmware_paths: tuple[str, ...] = ()

    @property
    def wanted_names(self) -> set[str]:
        return {name.lower() for name in (*self.exe_names, *self.flatpak_ids)}

    def expanded_search_paths(self) -> list[Path]:
        paths: list[Path] = []
        for value in self.search_paths:
            expanded = os.path.expanduser(os.path.expandvars(value))
            if os.name != "nt" and expanded.startswith("%"):
                continue
            paths.append(Path(expanded))
        if os.name != "nt":
            home = Path.home()
            for name in self.exe_names:
                if name.lower().endswith(".exe"):
                    continue
                which = shutil.which(name)
                if which:
                    paths.append(Path(which))
                for folder in (
                    Path("/usr/bin"),
                    Path("/usr/local/bin"),
                    Path("/usr/games"),
                    home / ".local" / "bin",
                    home / "Applications",
                ):
                    paths.append(folder / name)
            for app_id in self.flatpak_ids:
                paths.append(Path("/var/lib/flatpak/exports/bin") / app_id)
                paths.append(home / ".local" / "share" / "flatpak" / "exports" / "bin" / app_id)
        return paths

    def expanded_firmware_paths(self, executable: str) -> list[Path]:
        base = Path(executable).parent if executable else Path.home()
        paths: list[Path] = []
        for value in self.firmware_paths:
            expanded = os.path.expanduser(os.path.expandvars(value))
            if os.name != "nt" and expanded.startswith("%"):
                continue
            path = Path(expanded)
            if not path.is_absolute():
                path = base / path
            paths.append(path)
        return paths


PROFILES: tuple[EmulatorProfile, ...] = (
    EmulatorProfile(
        key="longshot",
        name="Longshot",
        system="Ports",
        system_key="ports",
        exe_names=("longshot.exe", "longshot", "longshot.appimage"),
        arguments=(),
        working_dir="exe_parent",
        priority=4,
        auto_scan=False,
        accent="#9B8BF4",
        description="Recreación nativa de Ocarina of Time para PC (sucesor de Hookshot).",
        note="Longshot se instala con su propio launcher; se lanza el juego ya compilado.",
    ),
    EmulatorProfile(
        key="hookshot",
        name="Hookshot",
        system="Ports",
        system_key="ports",
        exe_names=("hookshot.exe", "hookshot", "hookshot.appimage"),
        arguments=(),
        working_dir="hookshot_root",
        priority=5,
        auto_scan=False,
        accent="#E9B949",
        description="Port nativo para PC.",
    ),
    EmulatorProfile(
        key="dusklight",
        name="Dusklight",
        system="Ports",
        system_key="ports",
        exe_names=("dusklight.exe", "dusklight", "dusklight.appimage"),
        arguments=(),
        working_dir="exe_parent",
        priority=6,
        auto_scan=False,
        accent="#8B7CD8",
        description="Recreación nativa de Twilight Princess para PC.",
    ),
    EmulatorProfile(
        key="fritchii",
        name="Fritchii",
        system="Switch 2",
        system_key="switch2",
        exe_names=("lichii.exe", "fritchii.exe", "lichii", "fritchii"),
        arguments=("-g", "{rom}"),
        rom_extensions=(".nup", ".nsp", ".xci"),
        priority=10,
        accent="#6EA8FE",
        description="Juego de Switch 2 lanzado con Fritchii.",
    ),
    EmulatorProfile(
        key="rpcs3",
        name="RPCS3",
        system="PS3",
        system_key="ps3",
        exe_names=("rpcs3.exe", "rpcs3", "rpcs3.appimage"),
        arguments=("--no-gui", "{rom}"),
        rom_extensions=(".iso",),
        folder_markers=("PS3_GAME",),
        search_paths=(
            r"%LOCALAPPDATA%\Programs\RPCS3\rpcs3.exe",
            r"%LOCALAPPDATA%\rpcs3\rpcs3.exe",
            r"%PROGRAMFILES%\RPCS3\rpcs3.exe",
            r"%PROGRAMFILES(X86)%\RPCS3\rpcs3.exe",
        ),
        flatpak_ids=("net.rpcs3.RPCS3",),
        priority=15,
        accent="#5B8DEF",
        description="Juego de PlayStation 3 lanzado con RPCS3.",
        firmware_paths=("dev_flash", r"%APPDATA%\rpcs3\dev_flash", "~/.config/rpcs3/dev_flash"),
    ),
    EmulatorProfile(
        key="azahar",
        name="Azahar",
        system="3DS",
        system_key="3ds",
        exe_names=("azahar.exe", "azahar", "azahar.appimage"),
        rom_extensions=(".3ds", ".cci", ".cia", ".cxi"),
        search_paths=(
            r"%PROGRAMFILES%\Azahar\azahar.exe",
            r"%PROGRAMFILES(X86)%\Azahar\azahar.exe",
            r"%LOCALAPPDATA%\Azahar\azahar.exe",
            r"%LOCALAPPDATA%\Programs\Azahar\azahar.exe",
        ),
        flatpak_ids=("org.azahar_emu.Azahar",),
        priority=20,
        accent="#E05A7A",
        description="Juego de Nintendo 3DS lanzado con Azahar.",
    ),
    EmulatorProfile(
        key="dolphin",
        name="Dolphin",
        system="Wii",
        system_key="wii",
        systems=("gamecube",),
        exe_names=("dolphin.exe", "dolphin-emu.exe", "dolphin-emu", "dolphin-emu-qt2"),
        arguments=("-e", "{rom}"),
        rom_extensions=(".iso", ".rvz", ".wbfs", ".gcm", ".gcz"),
        search_paths=(
            r"%PROGRAMFILES%\Dolphin\Dolphin.exe",
            r"%LOCALAPPDATA%\Programs\Dolphin\Dolphin.exe",
            r"%LOCALAPPDATA%\Dolphin\Dolphin.exe",
        ),
        flatpak_ids=("org.DolphinEmu.dolphin-emu",),
        priority=30,
        accent="#6EC6A8",
        description="Juego de Wii o GameCube lanzado con Dolphin.",
    ),
    EmulatorProfile(
        key="pcsx2",
        name="PCSX2",
        system="PS2",
        system_key="ps2",
        exe_names=("pcsx2-qt.exe", "pcsx2.exe", "pcsx2-qt", "pcsx2", "pcsx2.appimage"),
        rom_extensions=(".iso", ".chd"),
        search_paths=(
            r"%LOCALAPPDATA%\Programs\PCSX2\pcsx2-qt.exe",
            r"%PROGRAMFILES%\PCSX2\pcsx2-qt.exe",
            r"%PROGRAMFILES(X86)%\PCSX2\pcsx2-qt.exe",
        ),
        flatpak_ids=("net.pcsx2.PCSX2",),
        priority=30,
        accent="#8B9DFF",
        description="Juego de PlayStation 2 lanzado con PCSX2.",
    ),
    EmulatorProfile(
        key="duckstation",
        name="DuckStation",
        system="PS1",
        system_key="ps1",
        exe_names=(
            "duckstation-qt-x64-releaseltcg.exe",
            "duckstation-qt.exe",
            "duckstation.exe",
            "duckstation-qt",
            "duckstation",
            "duckstation.appimage",
        ),
        rom_extensions=(".cue", ".pbp", ".chd"),
        search_paths=(
            r"%LOCALAPPDATA%\Programs\DuckStation\duckstation-qt-x64-ReleaseLTCG.exe",
            r"%PROGRAMFILES%\DuckStation\duckstation-qt-x64-ReleaseLTCG.exe",
        ),
        flatpak_ids=("org.duckstation.DuckStation",),
        priority=30,
        accent="#B8A6FF",
        description="Juego de PlayStation lanzado con DuckStation.",
    ),
    EmulatorProfile(
        key="ppsspp",
        name="PPSSPP",
        system="PSP",
        system_key="psp",
        exe_names=(
            "ppssppwindows64.exe",
            "ppssppwindows.exe",
            "ppsspp.exe",
            "ppsspp",
            "ppssppqt",
            "ppssppsdl",
        ),
        rom_extensions=(".iso", ".cso", ".pbp", ".chd"),
        search_paths=(
            r"%PROGRAMFILES%\PPSSPP\PPSSPPWindows64.exe",
            r"%LOCALAPPDATA%\Programs\PPSSPP\PPSSPPWindows64.exe",
        ),
        flatpak_ids=("org.ppsspp.PPSSPP",),
        priority=30,
        accent="#7ED0F0",
        description="Juego de PSP lanzado con PPSSPP.",
    ),
    EmulatorProfile(
        key="cemu",
        name="Cemu",
        system="Wii U",
        system_key="wiiu",
        exe_names=("cemu.exe", "cemu", "cemu.appimage"),
        arguments=("-g", "{rom}"),
        rom_extensions=(".wud", ".wux", ".wua", ".rpx"),
        search_paths=(
            r"%PROGRAMFILES%\Cemu\Cemu.exe",
            r"%LOCALAPPDATA%\Programs\Cemu\Cemu.exe",
        ),
        flatpak_ids=("info.cemu.Cemu",),
        priority=30,
        accent="#63D2C2",
        description="Juego de Wii U lanzado con Cemu.",
    ),
    EmulatorProfile(
        key="ryujinx",
        name="Ryujinx",
        system="Switch",
        system_key="switch",
        exe_names=("ryujinx.exe", "ryujinx", "ryujinx.appimage"),
        rom_extensions=(".nsp", ".xci", ".nro"),
        search_paths=(
            r"%LOCALAPPDATA%\Programs\Ryujinx\Ryujinx.exe",
            r"%PROGRAMFILES%\Ryujinx\Ryujinx.exe",
        ),
        flatpak_ids=("org.ryujinx.Ryujinx",),
        priority=40,
        accent="#74C0FC",
        description="Juego de Switch lanzado con Ryujinx.",
    ),
    EmulatorProfile(
        key="eden",
        name="Eden",
        system="Switch",
        system_key="switch",
        exe_names=("eden.exe", "eden", "eden.appimage"),
        arguments=("-f", "-g", "{rom}"),
        rom_extensions=(".nsp", ".xci", ".nro"),
        search_paths=(
            r"%LOCALAPPDATA%\Programs\Eden\eden.exe",
            r"%LOCALAPPDATA%\eden\eden.exe",
        ),
        priority=41,
        accent="#74C0FC",
        description="Juego de Switch lanzado con Eden.",
    ),
    EmulatorProfile(
        key="sudachi",
        name="Sudachi",
        system="Switch",
        system_key="switch",
        exe_names=("sudachi.exe", "sudachi", "sudachi.appimage"),
        arguments=("-f", "-g", "{rom}"),
        rom_extensions=(".nsp", ".xci", ".nro"),
        search_paths=(
            r"%LOCALAPPDATA%\Programs\Sudachi\sudachi.exe",
            r"%LOCALAPPDATA%\sudachi\sudachi.exe",
        ),
        priority=42,
        accent="#74C0FC",
        description="Juego de Switch lanzado con Sudachi.",
    ),
    EmulatorProfile(
        key="yuzu",
        name="Yuzu",
        system="Switch",
        system_key="switch",
        exe_names=("yuzu.exe", "suyu.exe", "yuzu", "suyu", "yuzu.appimage", "suyu.appimage"),
        arguments=("-f", "-g", "{rom}"),
        rom_extensions=(".nsp", ".xci", ".nro"),
        search_paths=(
            r"%LOCALAPPDATA%\yuzu\yuzu-windows-msvc\yuzu.exe",
            r"%LOCALAPPDATA%\Programs\yuzu\yuzu.exe",
        ),
        priority=44,
        accent="#74C0FC",
        description="Juego de Switch lanzado con Yuzu.",
    ),
    EmulatorProfile(
        key="melonds",
        name="melonDS",
        system="DS",
        system_key="nds",
        exe_names=("melonds.exe", "melonds", "melonds.appimage"),
        rom_extensions=(".nds",),
        search_paths=(
            r"%LOCALAPPDATA%\Programs\melonDS\melonDS.exe",
            r"%PROGRAMFILES%\melonDS\melonDS.exe",
        ),
        flatpak_ids=("net.kuribo64.melonDS",),
        priority=40,
        accent="#9BCB6E",
        description="Juego de Nintendo DS lanzado con melonDS.",
    ),
    EmulatorProfile(
        key="mgba",
        name="mGBA",
        system="GBA",
        system_key="gba",
        exe_names=("mgba.exe", "mgba-qt", "mgba"),
        rom_extensions=(".gba",),
        search_paths=(
            r"%PROGRAMFILES%\mGBA\mGBA.exe",
            r"%LOCALAPPDATA%\Programs\mGBA\mGBA.exe",
        ),
        flatpak_ids=("io.mgba.mGBA",),
        priority=40,
        accent="#B7D36B",
        description="Juego de Game Boy Advance lanzado con mGBA.",
    ),
    EmulatorProfile(
        key="lime3ds",
        name="Lime3DS",
        system="3DS",
        system_key="3ds",
        exe_names=("lime3ds.exe", "citra.exe", "lime3ds-gui", "lime3ds", "citra-qt", "citra"),
        rom_extensions=(".3ds", ".cci", ".cia", ".cxi"),
        search_paths=(
            r"%LOCALAPPDATA%\Programs\Lime3DS\lime3ds.exe",
            r"%PROGRAMFILES%\Lime3DS\lime3ds.exe",
        ),
        flatpak_ids=("io.github.lime3ds.Lime3DS", "org.citra_emu.citra"),
        priority=45,
        accent="#E05A7A",
        description="Juego de Nintendo 3DS lanzado con Lime3DS.",
    ),
    EmulatorProfile(
        key="soh",
        name="Ship of Harkinian",
        system="Ports",
        system_key="ports",
        exe_names=("soh.exe", "soh", "soh.appimage"),
        arguments=(),
        flatpak_ids=("org.shipofharkinian.ShipOfHarkinian",),
        priority=10,
        auto_scan=False,
        accent="#E9B949",
        description="Port nativo de Ocarina of Time.",
        note="Necesita la ROM original en el primer arranque.",
    ),
    EmulatorProfile(
        key="mame",
        name="MAME",
        system="Arcade",
        system_key="arcade",
        exe_names=("mame.exe", "mame64.exe", "mame"),
        arguments=("{rom}",),
        rom_extensions=(".zip",),
        search_paths=(
            r"%PROGRAMFILES%\MAME\mame.exe",
            r"%PROGRAMFILES(X86)%\MAME\mame.exe",
            r"%LOCALAPPDATA%\Programs\MAME\mame.exe",
        ),
        priority=35,
        accent="#D98C5F",
        description="Juego de arcade lanzado con MAME.",
        note="Los romsets deben estar en la carpeta roms de MAME.",
    ),
    EmulatorProfile(
        key="fbneo",
        name="FinalBurn Neo",
        system="Arcade",
        system_key="arcade",
        exe_names=("fbneo.exe", "fbn.exe", "fbneo", "fbn"),
        arguments=("{rom}",),
        rom_extensions=(".zip",),
        search_paths=(
            r"%PROGRAMFILES%\FinalBurn Neo\fbneo.exe",
            r"%LOCALAPPDATA%\Programs\FinalBurn Neo\fbneo.exe",
        ),
        priority=36,
        accent="#E0A95A",
        description="Juego de arcade o Neo Geo lanzado con FinalBurn Neo.",
    ),
    EmulatorProfile(
        key="snes9x",
        name="Snes9x",
        system="SNES",
        system_key="snes",
        exe_names=("snes9x-x64.exe", "snes9x.exe", "snes9x-gtk", "snes9x"),
        arguments=("{rom}",),
        rom_extensions=(".sfc", ".smc", ".zip"),
        search_paths=(
            r"%PROGRAMFILES%\Snes9x\snes9x-x64.exe",
            r"%LOCALAPPDATA%\Programs\Snes9x\snes9x-x64.exe",
        ),
        flatpak_ids=("com.snes9x.Snes9x",),
        priority=40,
        accent="#B48EAD",
        description="Juego de Super Nintendo lanzado con Snes9x.",
    ),
    EmulatorProfile(
        key="fceux",
        name="FCEUX",
        system="NES",
        system_key="nes",
        exe_names=("fceux.exe", "fceux"),
        arguments=("{rom}",),
        rom_extensions=(".nes", ".zip"),
        search_paths=(
            r"%PROGRAMFILES%\FCEUX\fceux.exe",
            r"%LOCALAPPDATA%\Programs\FCEUX\fceux.exe",
        ),
        priority=40,
        accent="#C97B84",
        description="Juego de NES lanzado con FCEUX.",
    ),
    EmulatorProfile(
        key="rmg",
        name="RMG",
        system="N64",
        system_key="n64",
        exe_names=("rmg.exe", "rmg", "rmg.appimage"),
        arguments=("{rom}",),
        rom_extensions=(".n64", ".z64", ".v64", ".zip"),
        search_paths=(
            r"%PROGRAMFILES%\RMG\RMG.exe",
            r"%LOCALAPPDATA%\Programs\RMG\RMG.exe",
        ),
        flatpak_ids=("com.github.Rosalie241.RMG",),
        priority=40,
        accent="#8FBF6A",
        description="Juego de Nintendo 64 lanzado con RMG.",
    ),
    EmulatorProfile(
        key="simple64",
        name="simple64",
        system="N64",
        system_key="n64",
        exe_names=("simple64-gui.exe", "simple64.exe", "simple64-gui", "simple64"),
        arguments=("{rom}",),
        rom_extensions=(".n64", ".z64", ".v64", ".zip"),
        search_paths=(
            r"%PROGRAMFILES%\simple64\simple64-gui.exe",
            r"%LOCALAPPDATA%\Programs\simple64\simple64-gui.exe",
        ),
        priority=45,
        accent="#9CCB72",
        description="Juego de Nintendo 64 lanzado con simple64.",
    ),
    EmulatorProfile(
        key="flycast",
        name="Flycast",
        system="Dreamcast",
        system_key="dreamcast",
        exe_names=("flycast.exe", "flycast", "flycast.appimage"),
        arguments=("{rom}",),
        rom_extensions=(".gdi", ".cdi", ".chd", ".zip"),
        search_paths=(
            r"%PROGRAMFILES%\Flycast\flycast.exe",
            r"%LOCALAPPDATA%\Programs\Flycast\flycast.exe",
        ),
        flatpak_ids=("org.flycast.Flycast",),
        priority=40,
        accent="#7EC8E3",
        description="Juego de Dreamcast lanzado con Flycast.",
    ),
    EmulatorProfile(
        key="kega",
        name="Kega Fusion",
        system="Mega Drive / Genesis",
        system_key="genesis",
        exe_names=("fusion.exe", "fusion"),
        arguments=("{rom}",),
        rom_extensions=(".md", ".gen", ".bin", ".sms", ".gg", ".iso", ".zip"),
        systems=("mastersystem", "gamegear"),
        priority=40,
        accent="#7FA6D9",
        description="Juego de Sega lanzado con Kega Fusion.",
    ),
    EmulatorProfile(
        key="desmume",
        name="DeSmuME",
        system="DS",
        system_key="nds",
        exe_names=("desmume.exe", "desmume_x64.exe", "desmume", "desmume-glade"),
        arguments=("{rom}",),
        rom_extensions=(".nds", ".zip"),
        search_paths=(
            r"%PROGRAMFILES%\DeSmuME\DeSmuME.exe",
            r"%PROGRAMFILES(X86)%\DeSmuME\DeSmuME.exe",
        ),
        flatpak_ids=("org.desmume.DeSmuME",),
        priority=45,
        accent="#9BCB6E",
        description="Juego de Nintendo DS lanzado con DeSmuME.",
    ),
    EmulatorProfile(
        key="vbam",
        name="VBA-M",
        system="GBA",
        system_key="gba",
        exe_names=("visualboyadvance-m.exe", "vbam.exe", "visualboyadvance-m", "vbam"),
        arguments=("{rom}",),
        rom_extensions=(".gba", ".gb", ".gbc", ".zip"),
        search_paths=(
            r"%PROGRAMFILES%\VisualBoyAdvance-M\visualboyadvance-m.exe",
            r"%LOCALAPPDATA%\Programs\VisualBoyAdvance-M\visualboyadvance-m.exe",
        ),
        flatpak_ids=("com.visualboyadvance_m.visualboyadvance-m",),
        priority=45,
        accent="#B7D36B",
        description="Juego de Game Boy lanzado con VBA-M.",
    ),
    EmulatorProfile(
        key="mednafen",
        name="Mednafen",
        system="Multi",
        system_key="multi",
        exe_names=("mednafen.exe", "mednafen"),
        arguments=("{rom}",),
        rom_extensions=(".cue", ".chd", ".pce", ".zip"),
        systems=("nes", "snes", "gb", "gba", "nds", "genesis", "saturn", "ps1", "pce"),
        priority=60,
        accent="#C792EA",
        description="Juego lanzado con Mednafen.",
        note="Cubre Saturn, PC Engine, PS1 y otras consolas.",
    ),
    EmulatorProfile(
        key="ares",
        name="Ares",
        system="Multi",
        system_key="multi",
        exe_names=("ares.exe", "ares"),
        arguments=("{rom}",),
        rom_extensions=(
            ".sfc",
            ".smc",
            ".nes",
            ".n64",
            ".z64",
            ".v64",
            ".gb",
            ".gbc",
            ".gba",
            ".md",
            ".gen",
            ".cue",
            ".chd",
            ".pce",
            ".zip",
        ),
        systems=(
            "nes",
            "snes",
            "n64",
            "gb",
            "gbc",
            "gba",
            "genesis",
            "mastersystem",
            "gamegear",
            "saturn",
            "ps1",
            "pce",
        ),
        priority=60,
        accent="#B39DDB",
        description="Juego lanzado con Ares.",
        note="Cubre NES, SNES, N64, Game Boy, Mega Drive, Saturn, PS1 y PC Engine.",
    ),
    EmulatorProfile(
        key="vice",
        name="VICE",
        system="Commodore 64",
        system_key="c64",
        exe_names=("x64sc.exe", "x64.exe", "vice.exe", "x64sc", "x64"),
        arguments=("{rom}",),
        rom_extensions=(".d64", ".crt", ".tap", ".prg", ".zip"),
        search_paths=(
            r"%PROGRAMFILES%\VICE\x64sc.exe",
            r"%PROGRAMFILES(X86)%\VICE\x64sc.exe",
        ),
        priority=40,
        accent="#8D9BB5",
        description="Juego de Commodore 64 lanzado con VICE.",
    ),
    EmulatorProfile(
        key="fsuae",
        name="FS-UAE",
        system="Amiga",
        system_key="amiga",
        exe_names=("fs-uae.exe", "fs-uae"),
        arguments=("--floppy_drive_0={rom}",),
        rom_extensions=(".adf", ".ipf", ".lha", ".zip"),
        search_paths=(
            r"%PROGRAMFILES%\FS-UAE\fs-uae.exe",
            r"%PROGRAMFILES(X86)%\FS-UAE\fs-uae.exe",
        ),
        priority=40,
        accent="#C79A7A",
        description="Juego de Amiga lanzado con FS-UAE.",
        note="Para .lha usa --hard_drive_0 en los argumentos.",
    ),
    EmulatorProfile(
        key="openmsx",
        name="openMSX",
        system="MSX",
        system_key="msx",
        exe_names=("openmsx.exe", "openmsx"),
        arguments=("-cart", "{rom}"),
        rom_extensions=(".rom", ".dsk", ".cas", ".zip"),
        priority=40,
        accent="#D0A46A",
        description="Juego de MSX lanzado con openMSX.",
        note="Para discos usa -diska en lugar de -cart.",
    ),
    EmulatorProfile(
        key="stella",
        name="Stella",
        system="Atari 2600",
        system_key="atari2600",
        exe_names=("stella.exe", "stella"),
        arguments=("{rom}",),
        rom_extensions=(".a26", ".bin", ".zip"),
        search_paths=(
            r"%PROGRAMFILES%\Stella\stella.exe",
            r"%PROGRAMFILES(X86)%\Stella\stella.exe",
        ),
        flatpak_ids=("io.github.stella_emu.Stella",),
        priority=40,
        accent="#D9A05B",
        description="Juego de Atari 2600 lanzado con Stella.",
    ),
    EmulatorProfile(
        key="xemu",
        name="xemu",
        system="Xbox",
        system_key="xbox",
        exe_names=("xemu.exe", "xemu", "xemu.appimage"),
        arguments=("-dvd_path", "{rom}"),
        rom_extensions=(".iso",),
        flatpak_ids=("app.xemu.xemu",),
        priority=45,
        accent="#7FC08A",
        description="Juego de Xbox original lanzado con xemu.",
    ),
    EmulatorProfile(
        key="xenia",
        name="Xenia",
        system="Xbox 360",
        system_key="xbox360",
        exe_names=("xenia.exe", "xenia_canary.exe", "xenia", "xenia_canary"),
        arguments=("{rom}",),
        rom_extensions=(".iso",),
        priority=45,
        accent="#8CCB8C",
        description="Juego de Xbox 360 lanzado con Xenia.",
    ),
    EmulatorProfile(
        key="vita3k",
        name="Vita3K",
        system="PS Vita",
        system_key="psvita",
        exe_names=("vita3k.exe", "vita3k", "vita3k.appimage"),
        arguments=("{rom}",),
        rom_extensions=(".vpk",),
        priority=50,
        accent="#6FA8DC",
        description="Juego de PS Vita lanzado con Vita3K.",
        note="Instala el .vpk en Vita3K antes de lanzarlo.",
    ),
    EmulatorProfile(
        key="retroarch",
        name="RetroArch",
        system="Multi",
        system_key="multi",
        exe_names=("retroarch.exe", "retroarch", "retroarch.appimage"),
        flatpak_ids=("org.libretro.RetroArch",),
        priority=90,
        auto_scan=False,
        accent="#C792EA",
        description="Juego lanzado con RetroArch.",
        note="RetroArch puede pedirte el núcleo al arrancar.",
    ),
)

PROFILE_BY_KEY: dict[str, EmulatorProfile] = {profile.key: profile for profile in PROFILES}

def profile_from_dict(data: object) -> EmulatorProfile | None:
    if not isinstance(data, dict):
        return None
    name = str(data.get("name") or "").strip()
    key = str(data.get("key") or "").strip()
    if not name or not key:
        return None
    system_key = str(data.get("system_key") or "otros").strip() or "otros"
    system = str(data.get("system") or SYSTEM_LABELS.get(system_key, "Otro"))
    executable = str(data.get("executable") or "").strip()
    raw_arguments = data.get("arguments") or ("{rom}",)
    if isinstance(raw_arguments, str):
        parts = raw_arguments.split()
    else:
        parts = [str(part) for part in raw_arguments]
    arguments = tuple(part for part in parts if part) or ("{rom}",)
    extensions = tuple(
        ext if ext.startswith(".") else f".{ext}"
        for ext in (
            str(item).strip().lower()
            for item in (data.get("rom_extensions") or [])
            if str(item).strip()
        )
    )
    exe_names = (Path(executable).name.lower(),) if executable else ()
    return EmulatorProfile(
        key=key,
        name=name,
        system=system,
        system_key=system_key,
        exe_names=exe_names,
        arguments=arguments,
        rom_extensions=extensions,
        priority=60,
        auto_scan=True,
        description="Emulador propio",
        note=executable,
    )


def custom_profiles(stored: object) -> list[EmulatorProfile]:
    items = stored if isinstance(stored, list) else []
    result: list[EmulatorProfile] = []
    for item in items:
        profile = profile_from_dict(item)
        if profile is not None:
            result.append(profile)
    return result


def all_profiles(settings: object) -> list[EmulatorProfile]:
    stored = settings.get("custom_emulators", []) if isinstance(settings, dict) else []
    return [*PROFILES, *custom_profiles(stored)]
