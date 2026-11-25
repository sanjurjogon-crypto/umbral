from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..backdrops import BackdropOption, download_backdrop, fetch_thumbnail, search_backdrops
from ..models import Game


class _SearchWorker(QThread):
    found = Signal(list)

    def __init__(self, query: str, game: Game, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.query = query
        self.game = game

    def run(self) -> None:
        try:
            results = search_backdrops(self.query, game=self.game, max_results=12)
        except Exception:  # noqa: BLE001
            results = []
        if not self.isInterruptionRequested():
            self.found.emit(results)


class _ThumbWorker(QThread):
    ready = Signal(int, bytes)

    def __init__(self, options: list[BackdropOption], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.options = options

    def run(self) -> None:
        for idx, opt in enumerate(self.options):
            if self.isInterruptionRequested():
                return
            payload = fetch_thumbnail(opt.thumb_url)
            if payload and not self.isInterruptionRequested():
                self.ready.emit(idx, payload)


class _DownloadWorker(QThread):
    done = Signal(str)

    def __init__(self, url: str, game: Game, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.url = url
        self.game = game

    def run(self) -> None:
        path = download_backdrop(self.url, self.game)
        if not self.isInterruptionRequested():
            self.done.emit(str(path) if path is not None else "")


class _OptionCard(QFrame):
    clicked = Signal(int)

    def __init__(self, index: int, option: BackdropOption, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.index = index
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(244, 174)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.thumb = QLabel("Cargando...")
        self.thumb.setFixedSize(232, 130)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet("background: rgba(0, 0, 0, 0.35); border-radius: 6px;")
        layout.addWidget(self.thumb)

        meta = QHBoxLayout()
        meta.setContentsMargins(2, 0, 2, 0)
        title = QLabel(option.title or option.source)
        title.setObjectName("muted")
        title.setMaximumWidth(170)
        badge = QLabel(option.source)
        badge.setObjectName("tiny")
        meta.addWidget(title, 1)
        meta.addWidget(badge, 0, Qt.AlignRight)
        layout.addLayout(meta)

    def set_pixmap(self, payload: bytes) -> None:
        pix = QPixmap()
        if pix.loadFromData(payload):
            scaled = pix.scaled(232, 130, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.thumb.setPixmap(scaled)
            self.thumb.setText("")

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)
        super().mouseReleaseEvent(event)


class BackdropPickerDialog(QDialog):
    def __init__(self, game: Game, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game = game
        self.selected_path = ""
        self.restore_default = False
        self._options: list[BackdropOption] = []
        self._cards: list[_OptionCard] = []
        self._search_worker: Optional[_SearchWorker] = None
        self._thumb_worker: Optional[_ThumbWorker] = None
        self._download_worker: Optional[_DownloadWorker] = None

        self.setWindowTitle(f"Fondo para {game.title}")
        self.resize(820, 580)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.query_edit = QLineEdit(game.title)
        self.query_edit.setPlaceholderText("Buscar fondo por nombre del juego...")
        self.query_edit.returnPressed.connect(self._start_search)
        self.search_btn = QPushButton("Buscar")
        self.search_btn.setObjectName("primary")
        self.search_btn.setCursor(Qt.PointingHandCursor)
        self.search_btn.clicked.connect(self._start_search)
        top.addWidget(self.query_edit, 1)
        top.addWidget(self.search_btn)
        root.addLayout(top)

        self.status_label = QLabel("Buscando fondos en internet...")
        self.status_label.setObjectName("muted")
        root.addWidget(self.status_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        self.grid = QGridLayout(container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.scroll.setWidget(container)
        root.addWidget(self.scroll, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        if game.backdrop:
            restore_btn = QPushButton("Restaurar fondo por defecto")
            restore_btn.setObjectName("ghost")
            restore_btn.setCursor(Qt.PointingHandCursor)
            restore_btn.clicked.connect(self._restore)
            bottom.addWidget(restore_btn)
        bottom.addStretch(1)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setObjectName("ghost")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)
        root.addLayout(bottom)

        self._start_search()

    def _stop_workers(self) -> None:
        for worker in (self._thumb_worker, self._search_worker, self._download_worker):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(400)

    def _clear_grid(self) -> None:
        self._cards.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _start_search(self) -> None:
        query = self.query_edit.text().strip() or self.game.title
        self._stop_workers()
        self._clear_grid()
        self.status_label.setText(f"Buscando fondos para «{query}»...")
        self.search_btn.setEnabled(False)
        self._search_worker = _SearchWorker(query, self.game, self)
        self._search_worker.found.connect(self._on_results)
        self._search_worker.start()

    def _on_results(self, options: list[BackdropOption]) -> None:
        self.search_btn.setEnabled(True)
        self._options = options
        if not options:
            self.status_label.setText("No se encontraron fondos. Prueba a editar la búsqueda.")
            return
        self.status_label.setText(f"{len(options)} opciones encontradas. Haz clic en una para aplicarla:")
        for idx, opt in enumerate(options):
            card = _OptionCard(idx, opt, self)
            card.clicked.connect(self._pick_option)
            self.grid.addWidget(card, idx // 3, idx % 3)
            self._cards.append(card)
        self._thumb_worker = _ThumbWorker(options, self)
        self._thumb_worker.ready.connect(self._on_thumb)
        self._thumb_worker.start()

    def _on_thumb(self, idx: int, payload: bytes) -> None:
        if 0 <= idx < len(self._cards):
            self._cards[idx].set_pixmap(payload)

    def _pick_option(self, idx: int) -> None:
        if not (0 <= idx < len(self._options)):
            return
        if self._download_worker is not None and self._download_worker.isRunning():
            return
        opt = self._options[idx]
        self.status_label.setText("Descargando fondo seleccionado...")
        for card in self._cards:
            card.setEnabled(False)
        self._download_worker = _DownloadWorker(opt.url, self.game, self)
        self._download_worker.done.connect(self._on_downloaded)
        self._download_worker.start()

    def _on_downloaded(self, path: str) -> None:
        if path:
            self.selected_path = path
            self.accept()
            return
        for card in self._cards:
            card.setEnabled(True)
        self.status_label.setText("No se pudo descargar esa imagen. Prueba con otra opción.")

    def _restore(self) -> None:
        self.restore_default = True
        self.accept()

    def closeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._stop_workers()
        super().closeEvent(event)

    def reject(self) -> None:
        self._stop_workers()
        super().reject()
