from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..consoles import SYSTEM_LABELS
from ..launcher import validate
from ..models import Emulator, Game
from ..profiles import EmulatorProfile
from ..profiles import PROFILE_BY_KEY
from ..store import Store, format_seconds
from ..updater import UpdateInfo, relative_time
from .shelf import ShelfCanvas
from .style import active as active_style
from .widgets import (
    CardRow,
    EmptyState,
    FlowLayout,
    GameCard,
    HealthRow,
    HeroBanner,
    SectionHeader,
    StatTile,
)

SORT_OPTIONS = [
    ("title", "Alfabético"),
    ("played", "Última vez jugado"),
    ("hours", "Más horas jugadas"),
    ("sessions", "Más sesiones"),
    ("added", "Añadido recientemente"),
    ("year", "Año"),
]

STATE_OPTIONS = [
    ("", "Todos"),
    ("unplayed", "Sin jugar"),
    ("playing", "En curso"),
    ("finished", "Terminados"),
]

SORT_DEFAULT_ASC = {
    "title": True,
    "played": False,
    "hours": False,
    "sessions": False,
    "added": False,
    "year": False,
}


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
            continue
        child = item.layout()
        if child is not None:
            clear_layout(child)


def _scroll_page() -> tuple[QScrollArea, QWidget, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    content = QWidget()
    body = QVBoxLayout(content)
    body.setContentsMargins(32, 24, 32, 32)
    body.setSpacing(24)
    scroll.setWidget(content)
    return scroll, content, body


class HomePage(QWidget):
    play_requested = Signal(object)
    details_requested = Signal(object)
    add_requested = Signal()

    def __init__(self, store: Store, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self._filter = ""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll, _content, self.body = _scroll_page()
        outer.addWidget(scroll)

        self.hero = HeroBanner()
        self.hero.play_requested.connect(self.play_requested)
        self.hero.details_requested.connect(self.details_requested)
        self.body.addWidget(self.hero)

        self.rows = QVBoxLayout()
        self.rows.setSpacing(26)
        self.body.addLayout(self.rows)
        self.body.addStretch(1)

    def refresh(self) -> None:
        clear_layout(self.rows)
        games = self.store.games
        if self._filter:
            games = [game for game in games if game.system_key == self._filter]
        featured = self._featured(games)
        self.hero.set_game(featured)

        recent = sorted((game for game in games if game.last_played), key=lambda game: game.last_played, reverse=True)
        if featured is not None:
            recent = [game for game in recent if game.id != featured.id]
        recent = recent[:8]
        favorites = [game for game in games if game.favorite][:8]
        added = sorted(games, key=lambda game: game.added_at, reverse=True)[:8]

        if recent:
            self._add_row("Recientes", recent)
        if favorites:
            self._add_row("Favoritos", favorites)
        if added:
            self._add_row("Añadidos recientes", added)

        if not games:
            if self._filter:
                label = SYSTEM_LABELS.get(self._filter, self._filter)
                empty = EmptyState(
                    f"No hay juegos de {label}",
                    "Prueba con otro sistema desde la barra lateral.",
                )
                self.rows.addWidget(empty)
            else:
                empty = EmptyState(
                    "Aún no hay juegos",
                    "Umbral puede detectar tus emuladores y ports, o puedes añadir un juego a mano.",
                    "Añadir juego",
                )
                empty.action.connect(self.add_requested)
                self.rows.addWidget(empty)

    def set_filter(self, key: str) -> None:
        self._filter = key
        self.refresh()

    def current_filter(self) -> str:
        return self._filter

    def _featured(self, games: list[Game]) -> Optional[Game]:
        if not games:
            return None
        played = [game for game in games if game.last_played]
        if played:
            return max(played, key=lambda game: game.last_played)
        favorites = [game for game in games if game.favorite]
        if favorites:
            return favorites[0]
        return games[0]

    def _add_row(self, title: str, games: list[Game]) -> None:
        row = CardRow(title, games)
        row.play_requested.connect(self.play_requested)
        row.details_requested.connect(self.details_requested)
        self.rows.addWidget(row)


class LibraryPage(QWidget):
    play_requested = Signal(object)
    details_requested = Signal(object)
    add_requested = Signal()

    def __init__(self, store: Store, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self._filter = ""
        self._query = ""
        self._favorites_only = False
        self._favorites_filter = ""
        self._state_filter = ""
        self._sort_key = str(store.settings.get("sort_key", "title"))
        self._sort_asc = bool(store.settings.get("sort_asc", True))
        if self._sort_key not in SORT_DEFAULT_ASC:
            self._sort_key = "title"

        header = QWidget(self)
        header.setObjectName("shelfHeader")
        self.header = header
        header_body = QVBoxLayout(header)
        header_body.setContentsMargins(38, 22, 38, 12)
        header_body.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(18)

        title_box = QVBoxLayout()
        title_box.setSpacing(6)
        self.title_label = QLabel("Biblioteca")
        self.title_label.setObjectName("shelfWord")
        self.count_label = QLabel("")
        self.count_label.setObjectName("shelfCount")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.count_label)
        top_row.addLayout(title_box)
        top_row.addStretch(1)
        header_body.addLayout(top_row)

        sort_row = QHBoxLayout()
        sort_row.setSpacing(10)
        sort_row.addStretch(1)
        sort_label = QLabel("Ordenar por")
        sort_label.setObjectName("muted")
        self.sort_combo = QComboBox()
        self.sort_combo.setCursor(Qt.PointingHandCursor)
        for key, label in SORT_OPTIONS:
            self.sort_combo.addItem(label, key)
        combo_index = self.sort_combo.findData(self._sort_key)
        if combo_index >= 0:
            self.sort_combo.setCurrentIndex(combo_index)
        self.sort_combo.currentIndexChanged.connect(self._sort_changed)
        self.order_button = QPushButton()
        self.order_button.setObjectName("ghost")
        self.order_button.setCursor(Qt.PointingHandCursor)
        self.order_button.clicked.connect(self._toggle_order)
        self.state_combo = QComboBox()
        self.state_combo.setCursor(Qt.PointingHandCursor)
        for key, label in STATE_OPTIONS:
            self.state_combo.addItem(label, key)
        self.state_combo.currentIndexChanged.connect(self._state_changed)
        sort_row.addWidget(sort_label)
        sort_row.addWidget(self.sort_combo)
        sort_row.addWidget(self.order_button)
        sort_row.addSpacing(10)
        sort_row.addWidget(self.state_combo)
        header_body.addLayout(sort_row)
        self._sync_order_button()

        self.canvas = ShelfCanvas(self)
        self.canvas.activated.connect(self.play_requested)
        self.canvas.details_requested.connect(self.details_requested)
        self.canvas.selection_changed.connect(self._on_selection)

        self.info = QWidget(self)
        self.info.setObjectName("shelfInfo")
        info_body = QVBoxLayout(self.info)
        info_body.setContentsMargins(38, 4, 38, 18)
        info_body.setSpacing(6)
        self.info_title = QLabel("")
        self.info_title.setObjectName("shelfTitle")
        self.info_title.setAlignment(Qt.AlignCenter)
        self.info_title.setWordWrap(True)
        self.info_meta = QLabel("")
        self.info_meta.setObjectName("shelfMeta")
        self.info_meta.setAlignment(Qt.AlignCenter)
        self.info_meta.setWordWrap(True)
        self.info_actions = QHBoxLayout()
        self.info_actions.setSpacing(10)
        self.info_actions.setAlignment(Qt.AlignHCenter)
        self.play_button = QPushButton("Jugar ahora")
        self.play_button.setObjectName("primary")
        self.play_button.setCursor(Qt.PointingHandCursor)
        self.play_button.clicked.connect(self._play_current)
        self.details_button = QPushButton("Ver ficha")
        self.details_button.setObjectName("ghost")
        self.details_button.setCursor(Qt.PointingHandCursor)
        self.details_button.clicked.connect(self._details_current)
        self.info_actions.addWidget(self.play_button)
        self.info_actions.addWidget(self.details_button)
        info_body.addWidget(self.info_title)
        info_body.addWidget(self.info_meta)
        info_body.addSpacing(4)
        info_body.addLayout(self.info_actions)

        hint = QLabel("← →  moverse   ·   Enter  jugar   ·   I  detalles   ·   rueda del ratón")
        hint.setObjectName("shelfHint")
        hint.setAlignment(Qt.AlignCenter)
        self.bottom = QWidget(self)
        bottom_body = QVBoxLayout(self.bottom)
        bottom_body.setContentsMargins(0, 0, 0, 0)
        bottom_body.setSpacing(0)
        bottom_body.addWidget(self.info)
        bottom_body.addWidget(hint)

        self._empty = EmptyState(
            "No hay juegos en esta vista",
            "Prueba otro sistema, vuelve a detectar o añade un juego a mano.",
            "Añadir juego",
            parent=self,
        )
        self._empty.action.connect(self.add_requested)
        self._empty.hide()

    def resizeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().resizeEvent(event)
        self._layout_overlays()

    def _bottom_height(self, width: int) -> int:
        layout = self.bottom.layout()
        if layout is None:
            return self.bottom.sizeHint().height()
        if layout.hasHeightForWidth():
            return layout.totalHeightForWidth(width)
        return layout.sizeHint().height()

    def _layout_overlays(self) -> None:
        if not hasattr(self, "canvas"):
            return
        width = self.width()
        height = self.height()
        self.canvas.setGeometry(0, 0, width, height)
        header_h = self.header.sizeHint().height()
        self.header.setGeometry(0, 0, width, header_h)
        bottom_h = self._bottom_height(width)
        self.bottom.setGeometry(0, height - bottom_h, width, bottom_h)
        self.canvas.lower()
        self.header.raise_()
        self.bottom.raise_()
        if hasattr(self, "_empty"):
            self._empty.setGeometry(0, 0, width, height)
            if self._empty.isVisible():
                self._empty.raise_()

    def set_mode(self, favorites_only: bool) -> None:
        self._favorites_only = favorites_only
        self._favorites_filter = ""
        self.title_label.setText("Favoritos" if favorites_only else "Biblioteca")
        self.refresh()

    def current_filter(self) -> str:
        return self._favorites_filter if self._favorites_only else self._filter

    def set_filter(self, key: str) -> None:
        if self._favorites_only:
            self._favorites_filter = key or ""
        else:
            self._filter = key or ""
        self.refresh()

    def set_query(self, text: str) -> None:
        self._query = text
        if text.strip() and self._filter:
            self._filter = ""
        self.refresh()

    def _sort_changed(self, _index: int) -> None:
        key = self.sort_combo.currentData()
        if not key:
            return
        self._sort_key = str(key)
        self._sort_asc = SORT_DEFAULT_ASC.get(self._sort_key, True)
        self._save_sort()
        self._sync_order_button()
        self.refresh(reset=True)

    def _toggle_order(self) -> None:
        self._sort_asc = not self._sort_asc
        self._save_sort()
        self._sync_order_button()
        self.refresh(reset=True)

    def _state_changed(self, _index: int) -> None:
        self._state_filter = str(self.state_combo.currentData() or "")
        self.refresh(reset=True)

    def _save_sort(self) -> None:
        self.store.settings["sort_key"] = self._sort_key
        self.store.settings["sort_asc"] = self._sort_asc
        self.store.save_settings()

    def _sync_order_button(self) -> None:
        self.order_button.setText("↑ Ascendente" if self._sort_asc else "↓ Descendente")

    def _visible_games(self) -> list[Game]:
        games = self.store.games
        if self._favorites_only:
            games = [game for game in games if game.favorite]
        active_filter = self.current_filter()
        if active_filter:
            games = [game for game in games if game.system_key == active_filter]
        if self._state_filter:
            games = [game for game in games if game.state == self._state_filter]
        query = self._query.strip().lower()
        if query:
            games = [
                game
                for game in games
                if query in game.title.lower()
                or query in game.subtitle.lower()
                or query in game.genre.lower()
            ]
        games = sorted(games, key=lambda game: game.title.lower())
        reverse = not self._sort_asc
        if self._sort_key == "played":
            games.sort(key=lambda game: game.last_played or "", reverse=reverse)
        elif self._sort_key == "hours":
            games.sort(key=lambda game: game.playtime_seconds, reverse=reverse)
        elif self._sort_key == "sessions":
            games.sort(key=lambda game: game.sessions, reverse=reverse)
        elif self._sort_key == "added":
            games.sort(key=lambda game: game.added_at or "", reverse=reverse)
        elif self._sort_key == "year":
            games.sort(key=lambda game: game.year or 0, reverse=reverse)
        else:
            games.sort(key=lambda game: game.title.lower(), reverse=reverse)
        return games

    def _on_selection(self, game: Game) -> None:
        self.info_title.setText(game.title)
        bits = [game.system] if game.system else []
        if game.year:
            bits.append(str(game.year))
        if game.genre:
            bits.append(game.genre)
        if game.playtime_seconds:
            bits.append(game.playtime_text)
        self.info_meta.setText("     ·     ".join(bits))
        self._layout_overlays()

    def _play_current(self) -> None:
        game = self.canvas.current_game()
        if game is not None:
            self.play_requested.emit(game)

    def _details_current(self) -> None:
        game = self.canvas.current_game()
        if game is not None:
            self.details_requested.emit(game)

    def refresh(self, reset: bool = False) -> None:
        games = self._visible_games()
        self.count_label.setText(f"{len(games)} JUEGOS" if len(games) != 1 else "1 JUEGO")
        if not games:
            if self._favorites_only:
                self._empty.set_text(
                    "Todavía no hay favoritos",
                    "Abre la ficha de un juego y pulsa la estrella para guardarlo aquí.",
                    "",
                )
            else:
                self._empty.set_text(
                    "No hay juegos en esta vista",
                    "Prueba otro sistema, vuelve a detectar o añade un juego a mano.",
                    "Añadir juego",
                )
            self.canvas.hide()
            self.info.hide()
            self._empty.show()
            self._layout_overlays()
            return
        self._empty.hide()
        self.canvas.show()
        self.info.show()
        self.canvas.set_games(games)
        if reset:
            self.canvas.reset_position()
        game = self.canvas.current_game()
        if game is not None:
            self._on_selection(game)
        self._layout_overlays()

    def focus_canvas(self) -> None:
        self.canvas.setFocus(Qt.OtherFocusReason)


class StatsPage(QWidget):
    def __init__(self, store: Store, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.body = _scroll_page()
        outer.addWidget(scroll)

        title = QLabel("Estadísticas")
        title.setObjectName("h2")
        self.body.addWidget(title)

        self.tiles_row = QHBoxLayout()
        self.tiles_row.setSpacing(14)
        self.tiles: list[StatTile] = []
        for _ in range(4):
            tile = StatTile("0", "")
            self.tiles.append(tile)
            self.tiles_row.addWidget(tile)
        self.body.addLayout(self.tiles_row)

        self.body.addWidget(SectionHeader("Tiempo por sistema"))
        self.systems_box = QVBoxLayout()
        self.systems_box.setSpacing(10)
        self.body.addLayout(self.systems_box)

        self.body.addWidget(SectionHeader("Juego más jugado"))
        self.most_played_frame = QFrame()
        self.most_played_frame.setObjectName("tile")
        most_body = QVBoxLayout(self.most_played_frame)
        most_body.setContentsMargins(18, 16, 18, 16)
        most_body.setSpacing(4)
        self.most_played_title = QLabel("Todavía no hay datos")
        self.most_played_title.setStyleSheet(
            'font-family: "Cinzel"; font-size: 16px; font-weight: 500; letter-spacing: 1px;'
        )
        self.most_played_detail = QLabel("Juega algo y aquí aparecerá tu título con más horas.")
        self.most_played_detail.setObjectName("muted")
        most_body.addWidget(self.most_played_title)
        most_body.addWidget(self.most_played_detail)
        self.body.addWidget(self.most_played_frame)
        self.body.addStretch(1)

    def refresh(self) -> None:
        stats = self.store.stats()
        total = stats["total_seconds"]
        self.tiles[0].set_values(format_seconds(total), "Tiempo total")
        self.tiles[1].set_values(str(stats["sessions"]), "Sesiones")
        self.tiles[2].set_values(str(stats["games"]), "Juegos")
        self.tiles[3].set_values(str(len(stats["systems"])), "Sistemas")

        clear_layout(self.systems_box)
        systems: dict[str, int] = stats["systems"]
        if not systems:
            label = QLabel("Aún no hay tiempo registrado por sistema.")
            label.setObjectName("muted")
            self.systems_box.addWidget(label)
        else:
            largest = max(1, max(systems.values()))
            for name, seconds in sorted(systems.items(), key=lambda item: item[1], reverse=True):
                row = QWidget()
                row_body = QHBoxLayout(row)
                row_body.setContentsMargins(0, 0, 0, 0)
                row_body.setSpacing(14)
                name_label = QLabel(name)
                name_label.setFixedWidth(120)
                bar = QProgressBar()
                bar.setRange(0, largest)
                bar.setValue(seconds)
                bar.setTextVisible(False)
                value_label = QLabel(format_seconds(seconds))
                value_label.setObjectName("muted")
                value_label.setFixedWidth(100)
                value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                row_body.addWidget(name_label)
                row_body.addWidget(bar, 1)
                row_body.addWidget(value_label)
                self.systems_box.addWidget(row)

        most = stats["most_played"]
        if most is None:
            self.most_played_title.setText("Todavía no hay datos")
            self.most_played_detail.setText("Juega algo y aquí aparecerá tu título con más horas.")
        else:
            self.most_played_title.setText(most.title)
            self.most_played_detail.setText(
                f"{most.subtitle or most.system}   ·   {most.playtime_text}   ·   {most.sessions} sesiones"
            )


class HealthPage(QWidget):
    rescan_requested = Signal()
    relink_requested = Signal(object)

    def __init__(self, store: Store, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self.emulators: list[Emulator] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.body = _scroll_page()
        outer.addWidget(scroll)

    def set_emulators(self, emulators: list[Emulator]) -> None:
        self.emulators = emulators

    def refresh(self) -> None:
        clear_layout(self.body)

        header = QHBoxLayout()
        title = QLabel("Salud de la biblioteca")
        title.setObjectName("h2")
        header.addWidget(title)
        header.addStretch(1)
        rescan = QPushButton("Volver a detectar")
        rescan.setObjectName("ghost")
        rescan.setCursor(Qt.PointingHandCursor)
        rescan.clicked.connect(self.rescan_requested)
        header.addWidget(rescan)
        self.body.addLayout(header)

        issues: list[tuple[str, str, str, Optional[Game]]] = []
        for game in self.store.games:
            messages = validate(game)
            if messages:
                issues.append(("error", game.title, " ".join(messages), game))
        for emulator in self.emulators:
            if not emulator.found:
                issues.append(("warn", emulator.name, emulator.note or "No se encontró el ejecutable.", None))

        for emulator in self.emulators:
            if emulator.key in ("hookshot", "retroarch"):
                continue
            if not any(game.system_key == emulator.system_key for game in self.store.games):
                issues.append(
                    (
                        "info",
                        emulator.name,
                        f"Emulador detectado, pero no hay juegos de {emulator.system} en las carpetas escaneadas.",
                        None,
                    )
                )

        for emulator in self.emulators:
            profile = PROFILE_BY_KEY.get(emulator.key)
            if not profile or not profile.firmware_paths:
                continue
            if not any(path.exists() for path in profile.expanded_firmware_paths(emulator.executable)):
                issues.append(
                    (
                        "warn",
                        emulator.name,
                        "Detectado, pero falta el firmware. Instálalo desde el propio emulador.",
                        None,
                    )
                )

        if not issues:
            self.body.addWidget(
                HealthRow("ok", "Todo en orden", "Los ejecutables y los archivos de tus juegos están en su sitio.")
            )
        else:
            for level, title_text, detail, game in issues:
                if game is not None:
                    row = HealthRow(level, title_text, detail, "Reasignar")
                    row.action_clicked.connect(
                        lambda _checked=False, target=game: self.relink_requested.emit(target)
                    )
                    self.body.addWidget(row)
                else:
                    self.body.addWidget(HealthRow(level, title_text, detail))

        self.body.addWidget(SectionHeader("Emuladores y ports"))
        for emulator in self.emulators:
            level = "ok" if emulator.found else "warn"
            detail = emulator.executable if emulator.found else (emulator.note or "Sin ruta configurada.")
            self.body.addWidget(HealthRow(level, emulator.name, detail))

        self.body.addStretch(1)


class SettingsPage(QWidget):
    accent_changed = Signal(str)
    style_changed = Signal(str)
    rescan_requested = Signal()
    scan_pc_requested = Signal()
    covers_requested = Signal()
    manage_emulators = Signal()
    open_data = Signal()
    export_diagnostics = Signal()
    check_updates = Signal()
    install_update = Signal()
    later_update = Signal()

    def __init__(self, store: Store, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self.emulators: list[Emulator] = []
        self.profiles: list[EmulatorProfile] = []
        self.available_update: Optional[UpdateInfo] = None
        self.update_checking = False
        self.update_message = ""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.body = _scroll_page()
        outer.addWidget(scroll)

    def set_emulators(self, emulators: list[Emulator]) -> None:
        self.emulators = emulators

    def set_profiles(self, profiles: list[EmulatorProfile]) -> None:
        self.profiles = profiles

    def refresh(self) -> None:
        clear_layout(self.body)

        title = QLabel("Ajustes")
        title.setObjectName("h2")
        self.body.addWidget(title)

        self.body.addWidget(SectionHeader("Actualizaciones"))
        update_tile = QFrame()
        update_tile.setObjectName("tile")
        update_row = QHBoxLayout(update_tile)
        update_row.setContentsMargins(16, 12, 16, 12)
        update_row.setSpacing(12)
        update_text = QVBoxLayout()
        update_text.setSpacing(2)
        version_label = QLabel(f"Umbral {__version__}")
        version_label.setStyleSheet("font-weight: 700;")
        status_text = self.update_message
        if not status_text:
            last = relative_time(str(self.store.settings.get("update_last_check", "")))
            status_text = f"Comprobado {last}" if last else "Sin comprobar todavía"
        status_label = QLabel(status_text)
        status_label.setObjectName("muted")
        status_label.setWordWrap(True)
        update_text.addWidget(version_label)
        update_text.addWidget(status_label)
        update_row.addLayout(update_text, 1)
        check_button = QPushButton(
            "Comprobando…" if self.update_checking else "Buscar actualizaciones"
        )
        check_button.setObjectName("ghost")
        check_button.setCursor(Qt.PointingHandCursor)
        check_button.setEnabled(not self.update_checking)
        check_button.clicked.connect(self.check_updates)
        update_row.addWidget(check_button)
        self.body.addWidget(update_tile)

        if self.available_update is not None:
            info = self.available_update
            card = QFrame()
            card.setObjectName("updateCard")
            card.setStyleSheet(
                f"QFrame#updateCard {{ border: 1px solid {active_style().accent}; "
                "border-radius: 10px; background: transparent; }}"
            )
            card_body = QVBoxLayout(card)
            card_body.setContentsMargins(16, 14, 16, 14)
            card_body.setSpacing(10)
            head = QHBoxLayout()
            head.setSpacing(10)
            heading = QLabel(f"Nueva versión {info.version}")
            heading.setStyleSheet(
                f"font-weight: 700; color: {active_style().accent};"
            )
            head.addWidget(heading, 1)
            page_button = QPushButton("Ver en GitHub")
            page_button.setObjectName("icon")
            page_button.setCursor(Qt.PointingHandCursor)
            page_button.clicked.connect(self._open_release_page)
            head.addWidget(page_button)
            card_body.addLayout(head)
            if info.notes:
                notes = QPlainTextEdit()
                notes.setReadOnly(True)
                notes.setPlainText(info.notes)
                notes.setFixedHeight(96)
                card_body.addWidget(notes)
            actions = QHBoxLayout()
            actions.setSpacing(10)
            later = QPushButton("Más tarde")
            later.setObjectName("ghost")
            later.setCursor(Qt.PointingHandCursor)
            later.clicked.connect(self.later_update)
            install = QPushButton("Actualizar ahora")
            install.setObjectName("primary")
            install.setCursor(Qt.PointingHandCursor)
            install.clicked.connect(self.install_update)
            actions.addWidget(later)
            actions.addStretch(1)
            actions.addWidget(install)
            card_body.addLayout(actions)
            self.body.addWidget(card)

        self.body.addWidget(SectionHeader("Emuladores y ports"))
        for emulator in self.emulators:
            frame = QFrame()
            frame.setObjectName("tile")
            row = QHBoxLayout(frame)
            row.setContentsMargins(16, 12, 16, 12)
            row.setSpacing(12)
            dot = QLabel("●")
            dot.setStyleSheet(
                f"color: {active_style().success}; font-size: 12px;"
                if emulator.found
                else f"color: {active_style().accent}; font-size: 12px;"
            )
            row.addWidget(dot)
            text = QVBoxLayout()
            text.setSpacing(2)
            name = QLabel(emulator.name)
            name.setStyleSheet("font-weight: 700;")
            path = QLabel(emulator.executable or emulator.note or "Sin ruta configurada")
            path.setObjectName("muted")
            path.setWordWrap(True)
            path.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            text.addWidget(name)
            text.addWidget(path)
            row.addLayout(text, 1)
            browse = QPushButton("Examinar")
            browse.setObjectName("icon")
            browse.setCursor(Qt.PointingHandCursor)
            browse.clicked.connect(lambda _checked=False, key=emulator.key: self._browse_executable(key))
            row.addWidget(browse)
            self.body.addWidget(frame)

        if not self.emulators:
            hint = QLabel("No hay emuladores detectados. Puedes indicar la ruta de cada uno a mano.")
            hint.setObjectName("tiny")
            hint.setWordWrap(True)
            self.body.addWidget(hint)
        manage = QPushButton("Añadir o detectar emulador")
        manage.setObjectName("ghost")
        manage.setCursor(Qt.PointingHandCursor)
        manage.clicked.connect(self.manage_emulators)
        self.body.addWidget(manage, 0, Qt.AlignLeft)

        self.body.addWidget(SectionHeader("Compatibles por consola"))
        groups: dict[tuple[str, str], list[EmulatorProfile]] = {}
        for profile in self.profiles:
            groups.setdefault((profile.system_key, profile.system), []).append(profile)
        found_keys = {emulator.key for emulator in self.emulators if emulator.found}
        for (_key, label), items in sorted(groups.items(), key=lambda item: item[0][1].lower()):
            frame = QFrame()
            frame.setObjectName("tile")
            row = QHBoxLayout(frame)
            row.setContentsMargins(16, 10, 16, 10)
            row.setSpacing(12)
            title = QLabel(label)
            title.setStyleSheet("font-weight: 700;")
            title.setMinimumWidth(190)
            row.addWidget(title)
            names = QVBoxLayout()
            names.setSpacing(2)
            for profile in items:
                found = profile.key in found_keys
                color = active_style().success if found else active_style().accent
                mark = "●" if found else "○"
                line = QLabel(f"{mark} {profile.name}")
                line.setStyleSheet(f"color: {color};")
                names.addWidget(line)
            row.addLayout(names, 1)
            self.body.addWidget(frame)
        if not self.profiles:
            hint = QLabel("Sin perfiles compatibles todavía.")
            hint.setObjectName("tiny")
            self.body.addWidget(hint)

        self.body.addWidget(SectionHeader("Carpetas escaneadas"))
        folders = self.store.settings.get("scan_folders", [])
        for folder in folders:
            frame = QFrame()
            frame.setObjectName("tile")
            row = QHBoxLayout(frame)
            row.setContentsMargins(16, 10, 16, 10)
            row.setSpacing(12)
            label = QLabel(folder)
            label.setObjectName("muted")
            label.setWordWrap(True)
            row.addWidget(label, 1)
            remove = QPushButton("Quitar")
            remove.setObjectName("icon")
            remove.setCursor(Qt.PointingHandCursor)
            remove.clicked.connect(lambda _checked=False, value=folder: self._remove_folder(value))
            row.addWidget(remove)
            self.body.addWidget(frame)
        add_folder = QPushButton("Añadir carpeta")
        add_folder.setObjectName("ghost")
        add_folder.setCursor(Qt.PointingHandCursor)
        add_folder.clicked.connect(self._add_folder)
        self.body.addWidget(add_folder, 0, Qt.AlignLeft)
        if not folders:
            hint = QLabel(
                "Sin carpetas propias: Umbral revisa Descargas, Escritorio, Documentos y Juegos."
            )
            hint.setObjectName("tiny")
            hint.setWordWrap(True)
            self.body.addWidget(hint)

        self.body.addWidget(SectionHeader("Juegos de PC"))
        pc_text = QLabel(
            "Umbral busca ejecutables .exe en tus carpetas y comprueba el nombre en Steam, "
            "itch.io y PCGamingWiki antes de proponerlos. También detecta descargas recientes "
            "de ROMs y te avisa si falta el emulador."
        )
        pc_text.setObjectName("muted")
        pc_text.setWordWrap(True)
        self.body.addWidget(pc_text)
        steam_check = QCheckBox("No proponer juegos que ya estén instalados en Steam")
        steam_check.setChecked(bool(self.store.settings.get("steam_scrape", True)))
        steam_check.toggled.connect(self._toggle_steam)
        self.body.addWidget(steam_check)
        scan_pc = QPushButton("Buscar juegos de PC")
        scan_pc.setObjectName("ghost")
        scan_pc.setCursor(Qt.PointingHandCursor)
        scan_pc.clicked.connect(self.scan_pc_requested)
        self.body.addWidget(scan_pc, 0, Qt.AlignLeft)

        self.body.addWidget(SectionHeader("Carátulas"))
        covers_text = QLabel(
            "Umbral descarga la carátula oficial de cada juego desde IGDB, Steam o itch.io. "
            "Si un juego aparece con un monograma, aún no tiene carátula."
        )
        covers_text.setObjectName("muted")
        covers_text.setWordWrap(True)
        self.body.addWidget(covers_text)
        covers_button = QPushButton("Buscar carátulas de nuevo")
        covers_button.setObjectName("ghost")
        covers_button.setCursor(Qt.PointingHandCursor)
        covers_button.clicked.connect(self.covers_requested)
        self.body.addWidget(covers_button, 0, Qt.AlignLeft)

        self.body.addWidget(SectionHeader("Datos y mantenimiento"))
        data_row = QHBoxLayout()
        data_row.setSpacing(10)
        open_data = QPushButton("Abrir carpeta de datos")
        open_data.setObjectName("ghost")
        open_data.setCursor(Qt.PointingHandCursor)
        open_data.clicked.connect(self.open_data)
        rescan = QPushButton("Volver a detectar")
        rescan.setObjectName("ghost")
        rescan.setCursor(Qt.PointingHandCursor)
        rescan.clicked.connect(self.rescan_requested)
        export = QPushButton("Exportar diagnóstico")
        export.setObjectName("ghost")
        export.setCursor(Qt.PointingHandCursor)
        export.clicked.connect(self.export_diagnostics)
        data_row.addWidget(open_data)
        data_row.addWidget(rescan)
        data_row.addWidget(export)
        data_row.addStretch(1)
        self.body.addLayout(data_row)
        note = QLabel(
            "Umbral no mueve tus ROMs ni tus partidas. Solo guarda rutas, tiempos de juego y preferencias."
        )
        note.setObjectName("tiny")
        note.setWordWrap(True)
        self.body.addWidget(note)
        self.body.addStretch(1)

    def _open_release_page(self) -> None:
        if self.available_update is not None:
            QDesktopServices.openUrl(QUrl(self.available_update.page_url))

    def set_update_checking(self, checking: bool) -> None:
        self.update_checking = checking
        if checking:
            self.update_message = "Comprobando en GitHub…"
        self.refresh()

    def set_update_available(self, info: UpdateInfo) -> None:
        self.available_update = info
        self.update_checking = False
        self.update_message = ""
        self.refresh()

    def set_update_result(self, message: str) -> None:
        self.update_checking = False
        self.update_message = message
        self.refresh()

    def dismiss_update(self) -> None:
        self.available_update = None
        self.update_message = "Actualización aplazada. Puedes comprobarla de nuevo cuando quieras."
        self.refresh()

    def _browse_executable(self, key: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona el ejecutable", "", "Ejecutables (*.exe);;Todos los archivos (*)"
        )
        if path:
            self.store.settings.setdefault("emulator_paths", {})[key] = path
            self.store.save_settings()
            self.rescan_requested.emit()

    def _toggle_steam(self, checked: bool) -> None:
        self.store.settings["steam_scrape"] = bool(checked)
        self.store.save_settings()

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Selecciona una carpeta de juegos")
        if folder:
            folders = self.store.settings.setdefault("scan_folders", [])
            if folder not in folders:
                folders.append(folder)
                self.store.save_settings()
                self.rescan_requested.emit()

    def _remove_folder(self, folder: str) -> None:
        folders = self.store.settings.setdefault("scan_folders", [])
        if folder in folders:
            folders.remove(folder)
            self.store.save_settings()
            self.rescan_requested.emit()
