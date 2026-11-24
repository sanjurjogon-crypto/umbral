from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..updater import UpdateCancelled, UpdateError, UpdateInfo, check_for_update, download_update


def _mb(value: int) -> str:
    number = value / (1024 * 1024)
    return f"{number:.1f}".replace(".", ",") + " MB"


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


class UpdateDownloadDialog(QDialog):
    def __init__(self, info: UpdateInfo, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.info = info
        self.downloaded_path = ""
        self.setWindowTitle("Actualizar Umbral")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMinimumHeight(230)

        body = QVBoxLayout(self)
        body.setContentsMargins(26, 24, 26, 22)
        body.setSpacing(12)

        title = QLabel(f"Umbral {info.version}")
        title.setObjectName("h2")
        body.addWidget(title)

        if info.notes:
            notes = QPlainTextEdit()
            notes.setReadOnly(True)
            notes.setPlainText(info.notes)
            notes.setFixedHeight(88)
            body.addWidget(notes)

        self.status = QLabel("Descargando la actualización…")
        self.status.setObjectName("muted")
        body.addWidget(self.status)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        body.addWidget(self.bar)

        self.detail = QLabel("")
        self.detail.setObjectName("tiny")
        body.addWidget(self.detail)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.open_page = QPushButton("Ver en GitHub")
        self.open_page.setObjectName("ghost")
        self.open_page.setCursor(Qt.PointingHandCursor)
        self.open_page.clicked.connect(self._open_page)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("ghost")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.clicked.connect(self._cancel)
        self.action = QPushButton("Reiniciar y actualizar")
        self.action.setObjectName("primary")
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.setEnabled(False)
        self.action.clicked.connect(self._accept)
        buttons.addWidget(self.open_page)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.action)
        body.addLayout(buttons)

        self.worker = DownloadWorker(info, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.bar.setValue(min(100, int(done * 100 / total)))
            self.detail.setText(f"{_mb(done)} de {_mb(total)}")
        else:
            self.detail.setText(_mb(done))

    def _on_done(self, path: str) -> None:
        self.downloaded_path = path
        self.bar.setValue(100)
        self.status.setText("Descarga comprobada. Umbral se reiniciará para instalarla.")
        self.action.setEnabled(True)
        self.cancel_button.setText("Cerrar")

    def _on_failed(self, message: str) -> None:
        self.status.setText(message)
        self.action.setEnabled(False)
        self.cancel_button.setText("Cerrar")

    def _on_cancelled(self) -> None:
        self.status.setText("Descarga cancelada.")
        self.action.setEnabled(False)
        self.cancel_button.setText("Cerrar")

    def _on_finished(self) -> None:
        if not self.downloaded_path:
            self.action.setEnabled(False)

    def _cancel(self) -> None:
        if self.worker.isRunning():
            self.status.setText("Cancelando…")
            self.worker.cancel()
            return
        self.reject()

    def _accept(self) -> None:
        if self.downloaded_path and Path(self.downloaded_path).is_file():
            self.accept()
        else:
            self.status.setText("La descarga aún no está lista.")

    def _open_page(self) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        if self.info.page_url.startswith("https://github.com/"):
            QDesktopServices.openUrl(QUrl(self.info.page_url))

    def closeEvent(self, event) -> None:
        if self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(2000)
        super().closeEvent(event)
