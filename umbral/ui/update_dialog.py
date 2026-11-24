from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from .. import __version__
from ..updater import UpdateCancelled, UpdateError, UpdateInfo, check_for_update, download_update


class CheckWorker(QThread):
    found = Signal(object)
    failed = Signal(str)

    def __init__(self, current: str = __version__, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current = current

    def run(self) -> None:
        try:
            info = check_for_update(self.current)
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("No se pudo comprobar si hay una versión nueva.")
        else:
            self.found.emit(info)


class DownloadWorker(QThread):
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, info: UpdateInfo, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.info = info
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            path = download_update(self.info, self.progress.emit, self._cancel)
        except UpdateCancelled:
            self.cancelled.emit()
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("No se pudo descargar la actualización.")
        else:
            self.done.emit(str(path))
