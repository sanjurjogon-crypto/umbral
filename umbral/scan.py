from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from . import downloads as downloads_module
from .detect import detect
from .index import invalidate
from .models import Game
from .standalone import (
    StandaloneCandidate,
    discover_standalone_games,
    verify_candidates,
)


class DetectWorker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        emulator_paths: dict[str, str] | None = None,
        scan_folders: list[str] | None = None,
        extra_profiles: list[object] | None = None,
        clear_cache: bool = False,
    ) -> None:
        super().__init__()
        self._emulator_paths = emulator_paths or {}
        self._scan_folders = scan_folders or []
        self._extra_profiles = extra_profiles or []
        self._clear_cache = clear_cache

    def run(self) -> None:
        try:
            if self._clear_cache:
                invalidate()
            self.done.emit(detect(self._emulator_paths, self._scan_folders, self._extra_profiles))
        except Exception as error:  # noqa: BLE001 - la detección no debe tumbar la app
            self.failed.emit(str(error))


class ScanWorker(QThread):
    progress = Signal(str)
    results = Signal(object, object, object, object)
    failed = Signal(str)

    def __init__(
        self,
        scan_folders: list[str] | None = None,
        include_steam: bool = True,
        include_downloads: bool = True,
        emulator_paths: dict[str, str] | None = None,
        extra_profiles: list[object] | None = None,
    ) -> None:
        super().__init__()
        self._scan_folders = scan_folders or []
        self._include_steam = include_steam
        self._include_downloads = include_downloads
        self._emulator_paths = emulator_paths or {}
        self._extra_profiles = extra_profiles or []

    def run(self) -> None:
        try:
            invalidate()
            self.progress.emit("Buscando ejecutables de juegos…")
            candidates: list[StandaloneCandidate] = discover_standalone_games(
                self._scan_folders, include_steam=self._include_steam
            )
            if candidates:
                self.progress.emit(f"Comprobando {len(candidates)} candidatos en internet…")
                verify_candidates(candidates)

            self.progress.emit("Buscando juegos de emuladores y ports…")
            emulated: list[Game] = []
            emulators = []
            try:
                detection = detect(self._emulator_paths, self._scan_folders, self._extra_profiles)
                emulated = list(detection.games)
                emulators = list(detection.emulators)
            except Exception:  # noqa: BLE001 - la detección no debe tumbar la búsqueda
                emulated = []

            pending = []
            if self._include_downloads:
                self.progress.emit("Revisando descargas recientes…")
                pending = downloads_module.pending_downloads(self._scan_folders)
            self.results.emit(candidates, pending, emulated, emulators)
        except Exception as error:  # noqa: BLE001 - el escaneo no debe tumbar la app
            self.failed.emit(str(error))
