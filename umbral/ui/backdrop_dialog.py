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
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..backdrops import BackdropOption, download_backdrop, fetch_thumbnail, search_backdrops
from ..models import Game


_ACTIVE_WORKERS: set[QThread] = set()


def _retire_worker(worker: Optional[QThread]) -> None:
    if worker is None:
        return
    try:
        for sig_name in ("found", "ready", "done"):
            sig = getattr(worker, sig_name, None)
            if sig is not None:
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
        if worker.isRunning():
            worker.requestInterruption()
            _ACTIVE_WORKERS.add(worker)
            worker.finished.connect(lambda w=worker: _cleanup_retired_worker(w))
        else:
            worker.deleteLater()
    except RuntimeError:
        pass


def _cleanup_retired_worker(worker: QThread) -> None:
    _ACTIVE_WORKERS.discard(worker)
    try:
        worker.deleteLater()
    except RuntimeError:
        pass


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
        upload_btn = QPushButton("Subir desde archivo…")
        upload_btn.setObjectName("ghost")
        upload_btn.setCursor(Qt.PointingHandCursor)
        upload_btn.clicked.connect(self._upload_local)
        bottom.addWidget(upload_btn)
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
        _retire_worker(self._thumb_worker)
        self._thumb_worker = None
        _retire_worker(self._search_worker)
        self._search_worker = None
        _retire_worker(self._download_worker)
        self._download_worker = None

    def _clear_grid(self) -> None:
        self._cards.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _start_search(self) -> None:
        query = self.game.title.strip() or self.game.title
        self._stop_workers()
        self._clear_grid()
        self.status_label.setText(f"Buscando fondos para «{query}»...")
        self._search_worker = _SearchWorker(query, self.game)
        self._search_worker.found.connect(self._on_results)
        self._search_worker.start()

    def _on_results(self, options: list[BackdropOption]) -> None:
        self._options = options
        if not options:
            self.status_label.setText("No se encontraron fondos para este juego.")
            return
        self.status_label.setText(f"{len(options)} opciones encontradas. Haz clic en una para aplicarla:")
        for idx, opt in enumerate(options):
            card = _OptionCard(idx, opt, self)
            card.clicked.connect(self._pick_option)
            self.grid.addWidget(card, idx // 3, idx % 3)
            self._cards.append(card)
        self._thumb_worker = _ThumbWorker(options)
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
        self._download_worker = _DownloadWorker(opt.url, self.game)
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

    def _upload_local(self) -> None:
        from PIL import Image, UnidentifiedImageError
        from PySide6.QtWidgets import QFileDialog
        from ..backdrops import backdrop_path

        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Elegir imagen de fondo",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not chosen:
            return
        try:
            with Image.open(chosen) as img:
                rgb = img.convert("RGB")
                target = backdrop_path(self.game)
                rgb.save(target, format="JPEG", quality=92, optimize=True)
                self.selected_path = str(target)
                self.accept()
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
            self.status_label.setText("No se pudo cargar esa imagen. Prueba con otro archivo.")

    def _restore(self) -> None:
        self.restore_default = True
        self.accept()

    def done(self, result: int) -> None:
        self._stop_workers()
        super().done(result)

    def closeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._stop_workers()
        super().closeEvent(event)

    def reject(self) -> None:
        self._stop_workers()
        super().reject()
