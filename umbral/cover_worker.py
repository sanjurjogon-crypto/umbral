from __future__ import annotations

import threading
from dataclasses import replace

from PySide6.QtCore import QThread, Signal

from .covers import fetch_covers
from .models import Game


class CoverWorker(QThread):
    progress = Signal(str)
    finished_with = Signal(int, int)

    def __init__(self, games: list[Game], missing_only: bool = True) -> None:
        super().__init__()
        self._games = list(games)
        self._missing_only = missing_only
        self._stop = threading.Event()

    def cancel(self) -> None:
        self._stop.set()
        self.requestInterruption()

    def run(self) -> None:
        snapshots = [replace(game) for game in self._games]
        try:
            if not self._stop.is_set():
                self.progress.emit("Buscando carátulas…")
            results, errors = fetch_covers(
                snapshots,
                missing_only=self._missing_only,
                stop_event=self._stop,
            )
        except Exception:  # noqa: BLE001 - una carátula no debe tumbar la app
            self.finished_with.emit(0, 0)
            return
        self.finished_with.emit(len(results), len(errors))
