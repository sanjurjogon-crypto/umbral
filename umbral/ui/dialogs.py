from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..detect import clean_title, profile_for_rom
from ..downloads import Download, describe as describe_download, emulator_for
from ..models import Emulator, Game, slugify
from ..rom_rules import is_ambiguous, validate_rom
from ..consoles import CONSOLE_EXTENSIONS, CONSOLES
from ..profiles import EmulatorProfile, all_profiles, profile_from_dict
from ..standalone import StandaloneCandidate, open_url
from ..store import Store
from .style import active as active_style
from .theme import ACCENTS
from .widgets import CoverArt

SYSTEMS = CONSOLES

PLACEHOLDER_COMPANY_TEXT = {
    "epic games, inc.",
    "epic games",
    "unity technologies",
    "defaultcompany",
    "default company",
    "your company",
}



class GameDetailDialog(QDialog):
    play_requested = Signal(object)
    edit_requested = Signal(object)
    delete_requested = Signal(object)
    changed = Signal()

    def __init__(self, game: Game, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game = game
        self.setWindowTitle(game.title)
        self.setModal(True)
        self.setMinimumSize(1240, 480)
        self.resize(1240, 520)

        body = QHBoxLayout(self)
        body.setContentsMargins(26, 26, 26, 26)
        body.setSpacing(26)

        cover = CoverArt(game, 240, 344)
        body.addWidget(cover, 0, Qt.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(8)

        kicker = QLabel(game.system.upper())
        kicker.setObjectName("kicker")
        right.addWidget(kicker)

        title = QLabel(game.title)
        title.setObjectName("h1")
        title.setWordWrap(True)
        right.addWidget(title)

        subtitle = QLabel(game.subtitle or game.system)
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        right.addWidget(subtitle)

        bits = []
        if game.year:
            bits.append(str(game.year))
        if game.genre:
            bits.append(game.genre)
        if game.emulator:
            bits.append(game.emulator)
        meta = QLabel("   ·   ".join(bits))
        meta.setObjectName("muted")
        right.addWidget(meta)

        divider = QLabel("")
        divider.setFixedHeight(10)
        right.addWidget(divider)

        description = QLabel(game.description or "Sin descripción todavía.")
        description.setObjectName("muted")
        description.setWordWrap(True)
        right.addWidget(description)

        right.addSpacing(8)
        stats = QHBoxLayout()
        stats.setSpacing(30)
        stats.addLayout(self._stat_block("Tiempo jugado", game.playtime_text))
        stats.addLayout(self._stat_block("Última sesión", game.last_played_text))
        stats.addLayout(self._stat_block("Sesiones", str(game.sessions)))
        right.addLayout(stats)

        right.addSpacing(8)
        self.recipe_toggle = QPushButton("Ver receta de lanzamiento")
        self.recipe_toggle.setObjectName("icon")
        self.recipe_toggle.setCursor(Qt.PointingHandCursor)
        self.recipe_toggle.clicked.connect(self._toggle_recipe)
        right.addWidget(self.recipe_toggle, 0, Qt.AlignLeft)

        self.recipe = QTextEdit()
        self.recipe.setReadOnly(True)
        self.recipe.setFont(QFont("Consolas", 9))
        self.recipe.setFixedHeight(116)
        self.recipe.setVisible(False)
        self.recipe.setPlainText(self._recipe_text())
        right.addWidget(self.recipe)

        right.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        play = QPushButton("Jugar ahora")
        play.setObjectName("primary")
        play.setCursor(Qt.PointingHandCursor)
        play.setMinimumWidth(play.sizeHint().width() + 10)
        play.clicked.connect(self._play)
        edit = QPushButton("Editar ficha")
        edit.setObjectName("ghost")
        edit.setCursor(Qt.PointingHandCursor)
        edit.setMinimumWidth(edit.sizeHint().width() + 10)
        edit.clicked.connect(self._edit)
        self.favorite_button = QPushButton()
        self.favorite_button.setObjectName("ghost")
        self.favorite_button.setCursor(Qt.PointingHandCursor)
        self.favorite_button.clicked.connect(self._toggle_favorite)
        self._update_favorite_button()
        self.progress_button = QPushButton()
        self.progress_button.setObjectName("ghost")
        self.progress_button.setCursor(Qt.PointingHandCursor)
        self.progress_button.clicked.connect(self._toggle_progress)
        self._update_progress_button()
        folder = QPushButton("Abrir carpeta")
        folder.setObjectName("ghost")
        folder.setCursor(Qt.PointingHandCursor)
        folder.setMinimumWidth(folder.sizeHint().width() + 10)
        folder.clicked.connect(self._open_folder)
        close = QPushButton("Cerrar")
        close.setObjectName("ghost")
        close.setCursor(Qt.PointingHandCursor)
        close.setMinimumWidth(close.sizeHint().width() + 10)
        close.clicked.connect(self.reject)
        remove = QPushButton("Quitar de Umbral")
        remove.setObjectName("ghost")
        remove.setCursor(Qt.PointingHandCursor)
        remove.setMinimumWidth(remove.sizeHint().width() + 10)
        remove.clicked.connect(self._remove)

        buttons.addWidget(play)
        buttons.addWidget(edit)
        buttons.addWidget(self.favorite_button)
        buttons.addWidget(self.progress_button)
        buttons.addStretch(1)
        buttons.addWidget(folder)
        buttons.addWidget(remove)
        buttons.addWidget(close)
        right.addLayout(buttons)

        body.addLayout(right, 1)

    def _stat_block(self, label: str, value: str) -> QVBoxLayout:
        block = QVBoxLayout()
        block.setSpacing(2)
        value_label = QLabel(value)
        value_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        label_widget = QLabel(label)
        label_widget.setObjectName("muted")
        label_widget.setStyleSheet("font-size: 11px;")
        block.addWidget(value_label)
        block.addWidget(label_widget)
        return block

    def _recipe_text(self) -> str:
        lines = [
            f"Comando: {self.game.command_preview}",
            f"Carpeta: {self.game.working_dir or '(sin carpeta)'}",
        ]
        if self.game.rom_path:
            lines.append(f"Juego: {self.game.rom_path}")
        return "\n".join(lines)

    def _toggle_recipe(self) -> None:
        visible = not self.recipe.isVisible()
        self.recipe.setVisible(visible)
        self.recipe_toggle.setText("Ocultar receta de lanzamiento" if visible else "Ver receta de lanzamiento")
        screen = self.screen()
        limit = screen.availableGeometry().height() - 80 if screen else 900
        target = self.height() + (124 if visible else -124)
        self.resize(self.width(), max(480, min(target, limit)))

    def _update_favorite_button(self) -> None:
        self.favorite_button.setText("★  En favoritos" if self.game.favorite else "☆  Favorito")
        self.favorite_button.setMinimumWidth(self.favorite_button.sizeHint().width() + 10)

    def _toggle_favorite(self) -> None:
        self.game.favorite = not self.game.favorite
        self._update_favorite_button()
        self.changed.emit()

    def _update_progress_button(self) -> None:
        text = "✓  Terminado" if self.game.progress == "finished" else "Marcar terminado"
        self.progress_button.setText(text)
        self.progress_button.setMinimumWidth(self.progress_button.sizeHint().width() + 10)

    def _toggle_progress(self) -> None:
        self.game.progress = "" if self.game.progress == "finished" else "finished"
        self._update_progress_button()
        self.changed.emit()

    def _play(self) -> None:
        self.play_requested.emit(self.game)
        self.accept()

    def _edit(self) -> None:
        self.edit_requested.emit(self.game)
        self.accept()

    def _remove(self) -> None:
        answer = QMessageBox.question(
            self,
            "Quitar de Umbral",
            f"¿Quitar «{self.game.title}» de la biblioteca?\n\n"
            "No se borra ningún archivo del juego.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.delete_requested.emit(self.game)
        self.accept()

    def _open_folder(self) -> None:
        candidates: list[str] = []
        if self.game.rom_path:
            rom = Path(self.game.rom_path)
            candidates.append(str(rom if rom.is_dir() else rom.parent))
        if self.game.working_dir:
            candidates.append(self.game.working_dir)
        if self.game.executable:
            candidates.append(str(Path(self.game.executable).parent))
        for folder in candidates:
            try:
                if folder and Path(folder).is_dir():
                    os.startfile(folder)
                    return
            except OSError:
                continue


class AddGameDialog(QDialog):
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        game: Optional[Game] = None,
        store: Optional[Store] = None,
        emulators: Optional[list[Emulator]] = None,
    ) -> None:
        super().__init__(parent)
        self._existing = game
        self._game: Optional[Game] = None
        self._store = store
        self._emulators = list(emulators or [])
        self._filling = False
        self._auto_title = ""
        self.setWindowTitle("Editar juego" if game else "Añadir juego")
        self.setModal(True)
        self.setMinimumWidth(690)

        body = QVBoxLayout(self)
        body.setContentsMargins(26, 24, 26, 22)
        body.setSpacing(12)

        title = QLabel("Editar juego" if game else "Añadir un juego")
        title.setObjectName("h2")
        body.addWidget(title)

        intro = QLabel(
            "Elige el archivo del juego o el ejecutable del port. Umbral rellena el sistema "
            "y busca el emulador instalado."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        body.addWidget(intro)

        basics = QGridLayout()
        basics.setHorizontalSpacing(14)
        basics.setVerticalSpacing(10)
        basics.setColumnStretch(1, 1)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Se rellena con el nombre del archivo")
        self.rom_edit = QLineEdit()
        self.rom_edit.setPlaceholderText("Archivo de ROM (.rvz, .3ds, .iso, .bin…) o el .exe de un port")
        self.rom_edit.editingFinished.connect(self._auto_fill)
        self.system_combo = QComboBox()
        for label, key in SYSTEMS:
            self.system_combo.addItem(label, key)
        self.system_combo.currentIndexChanged.connect(self._suggest_emulator)
        self.exe_edit = QLineEdit()
        self.exe_edit.setPlaceholderText("Ejecutable del emulador o del port")

        self._row(basics, 0, "Archivo del juego", self._rom_row())
        self._row(basics, 1, "Título", self.title_edit)
        self._row(basics, 2, "Sistema", self.system_combo)
        self._row(basics, 3, "Ejecutable", self._file_row(self.exe_edit, "exe"))
        body.addLayout(basics)

        self.status = QLabel("")
        self.status.setObjectName("tiny")
        self.status.setWordWrap(True)
        body.addWidget(self.status)

        self.advanced_button = QPushButton("Más opciones")
        self.advanced_button.setObjectName("ghost")
        self.advanced_button.setCheckable(True)
        self.advanced_button.setCursor(Qt.PointingHandCursor)
        self.advanced_button.toggled.connect(self._toggle_advanced)
        body.addWidget(self.advanced_button, 0, Qt.AlignLeft)

        self.advanced = QWidget()
        grid = QGridLayout(self.advanced)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        self.subtitle_edit = QLineEdit()
        self.subtitle_edit.setPlaceholderText("Se rellena con el sistema")
        self.working_edit = QLineEdit()
        self.arguments_edit = QPlainTextEdit()
        self.arguments_edit.setFixedHeight(68)
        self.arguments_edit.setPlaceholderText("Un argumento por línea. Usa {rom} para la ruta del juego.")
        self.genre_edit = QLineEdit()
        self.year_spin = QSpinBox()
        self.year_spin.setRange(0, 2100)
        self.year_spin.setSpecialValueText("Sin año")
        self.description_edit = QPlainTextEdit()
        self.description_edit.setFixedHeight(74)
        self.accent_combo = QComboBox()
        for name, color in ACCENTS:
            self.accent_combo.addItem(name, color)
        self._row(grid, 0, "Subtítulo", self.subtitle_edit)
        self._row(grid, 1, "Carpeta de trabajo", self._file_row(self.working_edit, "dir"))
        self._row(grid, 2, "Argumentos", self.arguments_edit)
        self._row(grid, 3, "Género", self.genre_edit)
        self._row(grid, 4, "Año", self.year_spin)
        self._row(grid, 5, "Descripción", self.description_edit)
        self._row(grid, 6, "Color", self.accent_combo)
        self.advanced.hide()
        body.addWidget(self.advanced)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("ghost")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save = QPushButton("Guardar")
        save.setObjectName("primary")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        body.addLayout(buttons)

        if game:
            self._fill(game)

    def _row(self, grid: QGridLayout, row: int, label: str, field: QWidget) -> None:
        label_widget = QLabel(label)
        label_widget.setObjectName("muted")
        label_widget.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid.addWidget(label_widget, row, 0)
        grid.addWidget(field, row, 1)

    def _file_row(self, line_edit: QLineEdit, mode: str) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(line_edit, 1)
        browse = QPushButton("Examinar")
        browse.setObjectName("icon")
        browse.setCursor(Qt.PointingHandCursor)
        if mode == "exe":
            browse.clicked.connect(lambda: self._browse_file(line_edit, "Ejecutables (*.exe);;Todos los archivos (*)"))
        else:
            browse.clicked.connect(lambda: self._browse_dir(line_edit))
        row.addWidget(browse)
        return container

    def _rom_row(self) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.rom_edit, 1)
        file_button = QPushButton("Archivo")
        file_button.setObjectName("icon")
        file_button.setCursor(Qt.PointingHandCursor)
        file_button.clicked.connect(self._browse_game_file)
        folder_button = QPushButton("Carpeta")
        folder_button.setObjectName("icon")
        folder_button.setCursor(Qt.PointingHandCursor)
        folder_button.clicked.connect(self._browse_game_folder)
        row.addWidget(file_button)
        row.addWidget(folder_button)
        return container

    def _game_file_filter(self) -> str:
        extensions = sorted(
            {extension.lstrip(".") for profile in self._profiles() for extension in profile.rom_extensions}
        )
        patterns = " ".join(f"*.{extension}" for extension in extensions)
        return f"Juegos y ejecutables ({patterns} *.exe);;Todos los archivos (*)"

    def _browse_game_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona el juego", "", self._game_file_filter()
        )
        if path:
            self.rom_edit.setText(path)
            self._auto_fill()

    def _browse_game_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta del juego")
        if path:
            self.rom_edit.setText(path)
            self._auto_fill()

    def _browse_file(self, line_edit: QLineEdit, file_filter: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecciona un archivo", "", file_filter)
        if path:
            line_edit.setText(path)

    def _browse_dir(self, line_edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Selecciona una carpeta")
        if path:
            line_edit.setText(path)

    def _profiles(self):
        settings = self._store.settings if self._store is not None else {}
        return all_profiles(settings)

    def _auto_fill(self) -> None:
        if self._filling or self._existing is not None:
            return
        raw = self.rom_edit.text().strip()
        if not raw:
            return
        path = Path(raw)
        profiles = self._profiles()
        suffix = path.suffix.lower()
        profile = None
        if suffix == ".exe":
            name = path.name.lower()
            profile = next((item for item in profiles if name in item.wanted_names), None)
        else:
            profile = profile_for_rom(path, profiles)

        self._filling = True
        try:
            if profile is not None:
                index = self.system_combo.findData(profile.system_key)
                if index >= 0:
                    self.system_combo.setCurrentIndex(index)
            elif suffix != ".exe":
                keys = [key for key, exts in CONSOLE_EXTENSIONS.items() if suffix in exts]
                if len(keys) == 1:
                    index = self.system_combo.findData(keys[0])
                    if index >= 0:
                        self.system_combo.setCurrentIndex(index)

            if not self.title_edit.text().strip() or self.title_edit.text() == self._auto_title:
                title = self._title_for(path, profile)
                self.title_edit.setText(title)
                self._auto_title = title

            system_key = str(self.system_combo.currentData() or "otros")
            if suffix == ".exe":
                if profile is None:
                    pc_index = self.system_combo.findData("pc")
                    if pc_index >= 0:
                        self.system_combo.setCurrentIndex(pc_index)
                    system_key = "pc"
                self.exe_edit.setText(str(path))
                if not self.subtitle_edit.text().strip() and profile is not None:
                    self.subtitle_edit.setText(f"{profile.system} · {profile.name}")
                if profile is not None:
                    self.status.setText(f"Port detectado: {profile.name}.")
                else:
                    self.status.setText("Juego de PC: se lanzará este ejecutable.")
            else:
                emulator = self._detected_emulator(system_key)
                if emulator is not None:
                    self.exe_edit.setText(emulator.executable)
                    emulator_profile = next(
                        (item for item in profiles if item.key == emulator.key), None
                    )
                    if (
                        emulator_profile is not None
                        and not self.arguments_edit.toPlainText().strip()
                    ):
                        self.arguments_edit.setPlainText(
                            chr(10).join(emulator_profile.arguments)
                        )
                    if (
                        emulator_profile is not None
                        and not self.subtitle_edit.text().strip()
                    ):
                        self.subtitle_edit.setText(
                            f"{emulator_profile.system} · {emulator_profile.name}"
                        )
                    self.status.setText(
                        f"Sistema {self.system_combo.currentText()} · emulador {emulator.name}."
                    )
                else:
                    self.status.setText(
                        f"Sistema {self.system_combo.currentText()}. No hay emulador detectado; "
                        "indícalo tú si hace falta."
                    )
        finally:
            self._filling = False

    def _title_for(self, path: Path, profile) -> str:
        ports = {
            "hookshot": "The Legend of Zelda: Ocarina of Time",
            "dusklight": "The Legend of Zelda: Twilight Princess",
            "soh": "The Legend of Zelda: Ocarina of Time (Ship of Harkinian)",
        }
        if profile is not None and profile.key in ports:
            return ports[profile.key]
        return clean_title(path.name)

    def _detected_emulator(self, system_key: str):
        for emulator in self._emulators:
            if not emulator.found or emulator.system_key != system_key:
                continue
            if emulator.executable and Path(emulator.executable).is_file():
                return emulator
        return None

    def _suggest_emulator(self, _index: int = 0) -> None:
        if self._filling or self._existing is not None:
            return
        if self.exe_edit.text().strip():
            return
        system_key = str(self.system_combo.currentData() or "")
        emulator = self._detected_emulator(system_key)
        if emulator is not None:
            self.exe_edit.setText(emulator.executable)

    def _toggle_advanced(self, checked: bool) -> None:
        self.advanced.setVisible(checked)
        self.advanced_button.setText("Menos opciones" if checked else "Más opciones")

    def _fill(self, game: Game) -> None:
        self.title_edit.setText(game.title)
        index = self.system_combo.findData(game.system_key)
        self.system_combo.setCurrentIndex(index if index >= 0 else 0)
        self.rom_edit.setText(game.rom_path)
        self.subtitle_edit.setText(game.subtitle)
        self.exe_edit.setText(game.executable)
        self.working_edit.setText(game.working_dir)
        self.arguments_edit.setPlainText(chr(10).join(game.arguments))
        self.genre_edit.setText(game.genre)
        self.year_spin.setValue(game.year or 0)
        self.description_edit.setPlainText(game.description)
        accent_index = self.accent_combo.findData(game.accent)
        self.accent_combo.setCurrentIndex(accent_index if accent_index >= 0 else 0)
        if game.working_dir or game.arguments or game.genre or game.year or game.description:
            self.advanced_button.setChecked(True)

    def _save(self) -> None:
        title = self.title_edit.text().strip()
        executable = self.exe_edit.text().strip()
        rom = self.rom_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Falta el título", "Escribe un título para el juego.")
            return
        if not executable and not rom:
            QMessageBox.warning(
                self,
                "Falta el juego",
                "Indica el archivo del juego o el ejecutable del emulador o del port.",
            )
            return

        system_label = self.system_combo.currentText().strip() or "Otro"
        system_key = str(self.system_combo.currentData() or "otros")
        if rom:
            rom_path = Path(rom)
            if rom_path.is_file():
                suffix = rom_path.suffix.lower()
                known = {
                    extension
                    for profile in self._profiles()
                    for extension in profile.rom_extensions
                }
                invalid_rom = (
                    suffix not in {".iso", ".chd"}
                    and is_ambiguous(rom_path)
                    and not validate_rom(
                        rom_path, "" if system_key == "otros" else system_key
                    )
                )
                unknown = suffix != ".exe" and suffix not in known
                if invalid_rom or unknown:
                    reason = (
                        "no parece una ROM válida para el sistema elegido"
                        if invalid_rom
                        else "no tiene una extensión de ROM conocida"
                    )
                    answer = QMessageBox.question(
                        self,
                        "Archivo poco habitual",
                        f"{rom_path.name} {reason}.\n\n"
                        "Puede ser un archivo de datos, un documento o una ROM dañada. "
                        "¿Añadirlo igualmente?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if answer != QMessageBox.Yes:
                        return
        arguments = [
            line.strip()
            for line in self.arguments_edit.toPlainText().splitlines()
            if line.strip()
        ]
        accent = str(self.accent_combo.currentData() or "#E9B949")
        subtitle = self.subtitle_edit.text().strip() or system_label
        genre = self.genre_edit.text().strip()
        year = self.year_spin.value() or None
        description = self.description_edit.toPlainText().strip()
        working_dir = self.working_edit.text().strip()
        if not working_dir and executable:
            working_dir = str(Path(executable).parent)
        if self._existing:
            game = self._existing
            game.title = title
            game.system = system_label
            game.system_key = system_key
            game.subtitle = subtitle
            game.executable = executable
            game.rom_path = rom
            game.working_dir = working_dir
            game.arguments = arguments
            game.genre = genre
            game.year = year
            game.description = description
            game.accent = accent
        else:
            game = Game(
                id=slugify(f"{system_key}-{title}-manual-{int(time.time())}"),
                title=title,
                system=system_label,
                system_key=system_key,
                subtitle=subtitle,
                executable=executable,
                rom_path=rom,
                working_dir=working_dir,
                arguments=arguments,
                genre=genre,
                year=year,
                description=description,
                accent=accent,
                source="manual",
            )
        self._game = game
        super().accept()

    def game(self) -> Optional[Game]:
        return self._game


class CustomEmulatorDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.data: dict[str, object] = {}
        self.setWindowTitle("Añadir emulador propio")
        self.setModal(True)
        self.setMinimumWidth(560)
        body = QVBoxLayout(self)
        body.setContentsMargins(24, 22, 24, 20)
        body.setSpacing(12)

        title = QLabel("Añadir emulador propio")
        title.setObjectName("h2")
        body.addWidget(title)
        intro = QLabel(
            "Dinos qué consola emula y cómo se lanza. Aparecerá en los compatibles de esa consola."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        body.addWidget(intro)

        self.console_combo = QComboBox()
        for label, key in CONSOLES:
            self.console_combo.addItem(label, key)
        self.console_combo.currentIndexChanged.connect(self._fill_extensions)
        body.addWidget(self._field("Consola", self.console_combo))

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nombre del emulador")
        body.addWidget(self._field("Nombre", self.name_edit))

        self.exe_edit = QLineEdit()
        self.exe_edit.setPlaceholderText("Ruta del ejecutable del emulador")
        exe_row = QWidget()
        exe_layout = QHBoxLayout(exe_row)
        exe_layout.setContentsMargins(0, 0, 0, 0)
        exe_layout.setSpacing(8)
        exe_layout.addWidget(self.exe_edit, 1)
        browse = QPushButton("Examinar")
        browse.setObjectName("ghost")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self._browse)
        exe_layout.addWidget(browse)
        body.addWidget(self._field("Ejecutable", exe_row))

        self.args_edit = QLineEdit("{rom}")
        body.addWidget(self._field("Argumentos", self.args_edit))

        self.ext_edit = QLineEdit()
        self.ext_edit.setPlaceholderText(".gba .zip")
        body.addWidget(self._field("Extensiones de ROM", self.ext_edit))

        note = QLabel(
            "Usa {rom} donde quieras la ruta del juego. Las extensiones van separadas por espacios o comas."
        )
        note.setObjectName("tiny")
        note.setWordWrap(True)
        body.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("ghost")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save = QPushButton("Añadir")
        save.setObjectName("primary")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        body.addLayout(buttons)
        self._fill_extensions()

    def _field(self, label_text: str, widget: QWidget) -> QWidget:
        frame = QWidget()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(label_text)
        label.setObjectName("tiny")
        layout.addWidget(label)
        layout.addWidget(widget)
        return frame

    def _fill_extensions(self) -> None:
        key = str(self.console_combo.currentData() or "")
        self.ext_edit.setText(" ".join(CONSOLE_EXTENSIONS.get(key, ())))

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecciona el ejecutable del emulador",
            "",
            "Ejecutables (*.exe);;Todos los archivos (*)",
        )
        if path:
            self.exe_edit.setText(path)
            if not self.name_edit.text().strip():
                self.name_edit.setText(Path(path).stem)

    def _accept(self) -> None:
        name = self.name_edit.text().strip()
        executable = self.exe_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Umbral", "Pon un nombre al emulador.")
            return
        if not executable:
            QMessageBox.warning(self, "Umbral", "Indica el ejecutable del emulador.")
            return
        if not Path(executable).is_file():
            QMessageBox.warning(self, "Umbral", f"No existe el ejecutable:\n{executable}")
            return
        raw = self.ext_edit.text().replace(",", " ")
        extensions = [part.strip().lower() for part in raw.split() if part.strip()]
        self.data = {
            "name": name,
            "system": self.console_combo.currentText(),
            "system_key": str(self.console_combo.currentData() or "otros"),
            "executable": executable,
            "arguments": self.args_edit.text().strip() or "{rom}",
            "rom_extensions": extensions,
        }
        super().accept()


class EmulatorChoiceDialog(QDialog):
    def __init__(
        self,
        game: Game,
        emulators: list[Emulator],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.chosen: Optional[Emulator] = None
        self.setWindowTitle("Elegir emulador")
        self.setModal(True)
        self.setMinimumWidth(560)
        body = QVBoxLayout(self)
        body.setContentsMargins(24, 22, 24, 20)
        body.setSpacing(10)

        title = QLabel(f"¿Con qué emulador abrimos {game.title}?")
        title.setObjectName("h2")
        title.setWordWrap(True)
        body.addWidget(title)
        intro = QLabel(f"{game.system} · varios emuladores compatibles")
        intro.setObjectName("muted")
        body.addWidget(intro)
        for emulator in emulators:
            button = QPushButton(f"{emulator.name}\n{emulator.executable}")
            button.setObjectName("ghost")
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet("text-align: left; padding: 12px 16px;")
            button.clicked.connect(
                lambda _checked=False, item=emulator: self._choose(item)
            )
            body.addWidget(button)
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("ghost")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        body.addWidget(cancel, 0, Qt.AlignRight)

    def _choose(self, emulator: Emulator) -> None:
        self.chosen = emulator
        super().accept()


class EmulatorSetupDialog(QDialog):
    def __init__(
        self,
        store: Store,
        emulators: list[Emulator],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.emulators = {emulator.key: emulator for emulator in emulators}
        self._profiles = all_profiles(store.settings)
        self._profile_by_key = {profile.key: profile for profile in self._profiles}
        self._custom_widgets: dict[str, QWidget] = {}
        stored_paths = store.settings.get("emulator_paths", {})
        self._paths = dict(stored_paths) if isinstance(stored_paths, dict) else {}
        self._labels: dict[str, QLabel] = {}
        self._statuses: dict[str, QLabel] = {}

        self.setWindowTitle("Emuladores y ports")
        self.setModal(True)
        self.setMinimumSize(820, 600)
        self.resize(900, 700)

        body = QVBoxLayout(self)
        body.setContentsMargins(26, 24, 26, 22)
        body.setSpacing(14)

        title = QLabel("Emuladores y ports")
        title.setObjectName("h2")
        body.addWidget(title)

        intro = QLabel(
            "Umbral guarda solo la ruta del ejecutable. No lo abre ni lo ejecuta al detectar. "
            "Si un emulador no aparece, indícalo aquí."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        body.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        rows = QVBoxLayout(content)
        rows.setContentsMargins(0, 0, 8, 0)
        rows.setSpacing(8)
        self._rows = rows
        for profile in self._profiles:
            custom = profile.key.startswith("custom-")
            widget = self._profile_row(profile, custom=custom)
            if custom:
                self._custom_widgets[profile.key] = widget
            rows.addWidget(widget)
        rows.addStretch(1)
        scroll.setWidget(content)
        body.addWidget(scroll, 1)

        add_custom = QPushButton("Añadir emulador propio")
        add_custom.setObjectName("ghost")
        add_custom.setCursor(Qt.PointingHandCursor)
        add_custom.clicked.connect(self._add_custom)
        body.addWidget(add_custom, 0, Qt.AlignLeft)

        note = QLabel(
            "Al guardar, Umbral vuelve a detectar todos los emuladores y juegos. "
            "Tus ROMs y partidas no se tocan."
        )
        note.setObjectName("tiny")
        note.setWordWrap(True)
        body.addWidget(note)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("ghost")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save = QPushButton("Guardar y detectar")
        save.setObjectName("primary")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        body.addLayout(buttons)

    def _profile_row(self, profile: EmulatorProfile, custom: bool = False) -> QWidget:
        found = self.emulators.get(profile.key)
        frame = QFrame()
        frame.setObjectName("tile")
        row = QHBoxLayout(frame)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(12)

        status = QLabel("●")
        status.setStyleSheet("font-size: 12px;")
        row.addWidget(status, 0, Qt.AlignTop)
        self._statuses[profile.key] = status

        text = QVBoxLayout()
        text.setSpacing(2)
        heading = QLabel(f"{profile.name}  ·  {profile.system}")
        heading.setStyleSheet("font-weight: 700;")
        text.addWidget(heading)

        path_label = QLabel("")
        path_label.setObjectName("muted")
        path_label.setWordWrap(True)
        path_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        text.addWidget(path_label)
        self._labels[profile.key] = path_label

        detail = profile.note
        if found and found.found and found.note:
            detail = found.note if not detail else f"{detail} · {found.note}"
        if detail:
            hint = QLabel(detail)
            hint.setObjectName("tiny")
            hint.setWordWrap(True)
            hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            text.addWidget(hint)
        row.addLayout(text, 1)

        browse = QPushButton("Examinar")
        browse.setObjectName("icon")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(lambda _checked=False, key=profile.key: self._browse(key))
        row.addWidget(browse)

        clear = QPushButton("Quitar")
        clear.setObjectName("icon")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(lambda _checked=False, key=profile.key: self._clear(key))
        row.addWidget(clear)

        if custom:
            delete = QPushButton("Eliminar")
            delete.setObjectName("icon")
            delete.setCursor(Qt.PointingHandCursor)
            delete.clicked.connect(
                lambda _checked=False, key=profile.key: self._remove_custom(key)
            )
            row.addWidget(delete)

        self._update_status(profile.key)
        return frame

    def _browse(self, key: str) -> None:
        profile = self._profile_by_key.get(key)
        name = profile.name if profile else key
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Selecciona el ejecutable de {name}",
            "",
            "Ejecutables (*.exe);;Todos los archivos (*)",
        )
        if path:
            self._paths[key] = path
            self._update_status(key)

    def _clear(self, key: str) -> None:
        self._paths.pop(key, None)
        self._update_status(key)

    def _update_status(self, key: str) -> None:
        label = self._labels[key]
        status = self._statuses[key]
        path = self._paths.get(key, "").strip()
        found = self.emulators.get(key)
        color = active_style().accent
        text = ""

        if path:
            candidate = Path(path)
            if not candidate.is_file():
                text = f"La ruta configurada no existe: {path}"
            elif key == "hookshot" and candidate.name.lower() == "hookshot.exe" and self._is_builder(candidate):
                text = "Parece el instalador de Hookshot Builder, no el juego."
            else:
                text = path
                color = active_style().success
        elif found and found.found:
            text = found.executable
            color = active_style().success
        elif found and found.note:
            text = found.note
        else:
            text = "Sin ruta configurada"

        status.setStyleSheet(f"color: {color}; font-size: 12px;")
        label.setText(self._breakable(text))

    def _breakable(self, text: str) -> str:
        return text.replace("\\", "\\\u200b").replace("/", "/\u200b")

    def _is_builder(self, path: Path) -> bool:
        try:
            return path.stat().st_size < 5_000_000
        except OSError:
            return False

    def _add_custom(self) -> None:
        dialog = CustomEmulatorDialog(self)
        if dialog.exec() != QDialog.Accepted or not dialog.data:
            return
        data = dict(dialog.data)
        stored = self.store.settings.get("custom_emulators", [])
        items = [item for item in stored if isinstance(item, dict)] if isinstance(stored, list) else []
        keys = {str(item.get("key") or "") for item in items}
        base = f"custom-{slugify(str(data.get('name') or 'emulador'))}"
        key = base
        index = 2
        while key in keys:
            key = f"{base}-{index}"
            index += 1
        data["key"] = key
        items.append(data)
        self.store.settings["custom_emulators"] = items
        profile = profile_from_dict(data)
        if profile is None:
            return
        self._profiles.append(profile)
        self._profile_by_key[profile.key] = profile
        self._paths[key] = str(data.get("executable") or "")
        widget = self._profile_row(profile, custom=True)
        self._custom_widgets[key] = widget
        self._rows.insertWidget(self._rows.count() - 1, widget)
        self.store.save_settings()

    def _remove_custom(self, key: str) -> None:
        stored = self.store.settings.get("custom_emulators", [])
        items = [item for item in stored if isinstance(item, dict)] if isinstance(stored, list) else []
        items = [item for item in items if str(item.get("key") or "") != key]
        self.store.settings["custom_emulators"] = items
        self._paths.pop(key, None)
        self._profiles = [profile for profile in self._profiles if profile.key != key]
        self._profile_by_key.pop(key, None)
        self._labels.pop(key, None)
        self._statuses.pop(key, None)
        widget = self._custom_widgets.pop(key, None)
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        self.store.save_settings()

    def _save(self) -> None:
        stored = self.store.settings.get("emulator_paths", {})
        overrides = stored if isinstance(stored, dict) else {}
        self.store.settings["emulator_paths"] = overrides
        for profile in self._profiles:
            value = self._paths.get(profile.key, "").strip()
            if value:
                overrides[profile.key] = value
            else:
                overrides.pop(profile.key, None)
        self.store.save_settings()
        super().accept()

class GameScanDialog(QDialog):
    add_requested = Signal(object)
    recheck_requested = Signal()

    def __init__(
        self,
        candidates: list[StandaloneCandidate],
        pending: list[Download],
        parent: Optional[QWidget] = None,
        emulated: Optional[list[object]] = None,
        stores: Optional[list[object]] = None,
    ) -> None:
        super().__init__(parent)
        self.candidates = candidates
        self.pending = pending
        self.emulated = emulated or []
        self.stores = stores or []
        self._boxes: dict[str, tuple[QCheckBox, object]] = {}
        self.setWindowTitle("Juegos encontrados")
        self.setModal(True)
        self.setMinimumSize(860, 620)
        self.resize(940, 720)

        body = QVBoxLayout(self)
        body.setContentsMargins(26, 24, 26, 22)
        body.setSpacing(14)

        title = QLabel("Juegos encontrados")
        title.setObjectName("h2")
        body.addWidget(title)

        intro = QLabel(
            "Umbral ha buscado juegos de PC, de Steam, de Epic Games, de emuladores y ports. "
            "Los ejecutables de PC se comprueban en Steam, itch.io y PCGamingWiki. "
            "Marca los que quieras añadir."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        body.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        rows = QVBoxLayout(content)
        rows.setContentsMargins(0, 0, 8, 0)
        rows.setSpacing(8)

        confirmed = [item for item in candidates if item.online_ok]
        unknown = [item for item in candidates if not item.online_ok]

        if self.stores:
            rows.addWidget(self._section("Steam y Epic Games"))
            for game in self.stores:
                rows.addWidget(self._emulated_row(game))

        if self.emulated:
            rows.addWidget(self._section("Emuladores y ports"))
            for game in self.emulated:
                rows.addWidget(self._emulated_row(game))

        if confirmed:
            rows.addWidget(self._section("Confirmados en internet"))
            for candidate in confirmed:
                rows.addWidget(self._candidate_row(candidate))

        if pending:
            rows.addWidget(self._section("Descargas y archivos sin juego"))
            for download in pending:
                rows.addWidget(self._download_row(download))

        if unknown:
            rows.addWidget(self._section("Sin coincidencia online · revisa antes de añadir"))
            for candidate in unknown:
                rows.addWidget(self._candidate_row(candidate))

        if not candidates and not pending and not self.emulated and not self.stores:
            empty = QLabel(
                "No se ha encontrado ningún juego nuevo. Si tienes juegos en otra carpeta, "
                "añádela en Ajustes y vuelve a escanear."
            )
            empty.setObjectName("muted")
            empty.setWordWrap(True)
            rows.addWidget(empty)

        rows.addStretch(1)
        scroll.setWidget(content)
        body.addWidget(scroll, 1)

        note = QLabel(
            "Umbral no mueve ni ejecuta nada al detectar: solo guarda la ruta del ejecutable."
        )
        note.setObjectName("tiny")
        note.setWordWrap(True)
        body.addWidget(note)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        recheck = QPushButton("Volver a comprobar")
        recheck.setObjectName("ghost")
        recheck.setCursor(Qt.PointingHandCursor)
        recheck.clicked.connect(self._recheck)
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("ghost")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        add = QPushButton("Añadir seleccionados")
        add.setObjectName("primary")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self._add)
        buttons.addWidget(recheck)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(add)
        body.addLayout(buttons)

    def _section(self, text: str) -> QWidget:
        from .widgets import SectionHeader

        return SectionHeader(text)

    def _recheck(self) -> None:
        self.recheck_requested.emit()
        self.accept()

    def _candidate_row(self, candidate: StandaloneCandidate) -> QWidget:
        frame = QFrame()
        frame.setObjectName("tile")
        row = QHBoxLayout(frame)
        row.setContentsMargins(14, 11, 14, 11)
        row.setSpacing(12)

        box = QCheckBox()
        box.setChecked(candidate.online_ok)
        key = str(candidate.executable).lower()
        self._boxes[key] = (box, candidate)
        row.addWidget(box, 0, Qt.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        heading = QLabel(candidate.display_title)
        heading.setStyleSheet("font-weight: 700;")
        heading.setWordWrap(True)
        text.addWidget(heading)

        bits = [candidate.confidence_label]
        if candidate.engine:
            engine_name = candidate.engine.split(" · ")[0]
            bits.append(engine_name)
        if candidate.company and candidate.company.strip().lower() not in PLACEHOLDER_COMPANY_TEXT:
            bits.append(candidate.company)
        meta = QLabel("   ·   ".join(part for part in bits if part))
        meta.setObjectName("muted")
        meta.setWordWrap(True)
        text.addWidget(meta)


        source = QLabel(self._source_text(candidate))
        source.setObjectName("tiny")
        source.setWordWrap(True)
        text.addWidget(source)

        path_label = QLabel(str(candidate.executable))
        path_label.setObjectName("tiny")
        path_label.setWordWrap(True)
        text.addWidget(path_label)
        row.addLayout(text, 1)

        if candidate.online_url:
            open_button = QPushButton("Abrir ficha")
            open_button.setObjectName("icon")
            open_button.setCursor(Qt.PointingHandCursor)
            open_button.clicked.connect(
                lambda _checked=False, url=candidate.online_url: open_url(url)
            )
            row.addWidget(open_button, 0, Qt.AlignTop)

        return frame

    def _emulated_row(self, game: Game) -> QWidget:
        frame = QFrame()
        frame.setObjectName("tile")
        row = QHBoxLayout(frame)
        row.setContentsMargins(14, 11, 14, 11)
        row.setSpacing(12)

        box = QCheckBox()
        box.setChecked(True)
        key = f"emulated::{game.id}"
        self._boxes[key] = (box, game)
        row.addWidget(box, 0, Qt.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        heading = QLabel(game.title)
        heading.setStyleSheet("font-weight: 700;")
        heading.setWordWrap(True)
        text.addWidget(heading)

        meta = QLabel(game.subtitle or game.system)
        meta.setObjectName("muted")
        meta.setWordWrap(True)
        text.addWidget(meta)

        if game.source in {"steam", "epic"}:
            origin = game.notes or game.executable
        else:
            origin = game.rom_path or game.executable or game.emulator
        path_label = QLabel(str(origin))
        path_label.setObjectName("tiny")
        path_label.setWordWrap(True)
        text.addWidget(path_label)
        row.addLayout(text, 1)
        return frame

    def _source_text(self, candidate: StandaloneCandidate) -> str:
        if candidate.online_status == "steam-local":
            return "Ya instalado en tu biblioteca de Steam"
        if candidate.online_status == "steam":
            return "Verificado en la tienda de Steam"
        if candidate.online_status == "itch":
            return "Verificado en itch.io"
        if candidate.online_status == "pcgamingwiki":
            return "Verificado en PCGamingWiki"
        if candidate.online_status == "offline":
            return "Sin conexión: no se pudo comprobar en internet"
        return "Sin coincidencia en Steam, itch.io ni PCGamingWiki"


    def _download_row(self, download: Download) -> QWidget:
        frame = QFrame()
        frame.setObjectName("tile")
        row = QHBoxLayout(frame)
        row.setContentsMargins(14, 11, 14, 11)
        row.setSpacing(12)

        profile = emulator_for(download.path)
        usable = not download.partial and profile is not None
        box = QCheckBox()
        box.setChecked(usable)
        box.setEnabled(usable)
        key = f"download::{str(download.path).lower()}"
        self._boxes[key] = (box, download)
        row.addWidget(box, 0, Qt.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        heading = QLabel(clean_title(download.path.name))
        heading.setStyleSheet("font-weight: 700;")
        heading.setWordWrap(True)
        text.addWidget(heading)
        if profile is None and not download.partial:
            detail_text = "Sistema no identificado. Añádelo a mano desde «Añadir juego»."
        else:
            detail_text = describe_download(download)
        detail = QLabel(detail_text)
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        text.addWidget(detail)
        path_label = QLabel(str(download.path))
        path_label.setObjectName("tiny")
        path_label.setWordWrap(True)
        text.addWidget(path_label)
        row.addLayout(text, 1)
        return frame

    def _add(self) -> None:
        selected: list[object] = []
        for box, item in self._boxes.values():
            if box.isChecked():
                selected.append(item)
        self.add_requested.emit(selected)
        super().accept()
