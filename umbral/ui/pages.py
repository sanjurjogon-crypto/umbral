from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..consoles import SYSTEM_LABELS
from ..launcher import validate
from ..models import Emulator, Game
from ..paths import executable_file_filter
from ..profiles import EmulatorProfile, PROFILE_BY_KEY, all_profiles
from ..store import Store, format_seconds
from ..stores import store_statuses
from ..updater import UpdateInfo, relative_time
from .shelf import ShelfCanvas, emulator_badge_pixmap
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
    apply_download_progress,
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

HOME_SHELVES = [
    ("En curso", "playing"),
    ("Sin jugar", "unplayed"),
    ("Terminados", "finished"),
]


def shelf_games(games: list[Game], state_key: str, limit: int = 8) -> list[Game]:
    selected = [game for game in games if game.state == state_key]
    if state_key == "unplayed":
        selected.sort(key=lambda game: game.added_at, reverse=True)
    elif state_key == "finished":
        selected.sort(
            key=lambda game: (game.last_played, game.playtime_seconds),
            reverse=True,
        )
    else:
        selected.sort(
            key=lambda game: (game.playtime_seconds, game.last_played),
            reverse=True,
        )
    return selected[:limit]

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
    context_requested = Signal(object, object)
    add_requested = Signal()
    backdrop_change_requested = Signal(object)

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
        self.rows.setSpacing(22)
        self.body.addLayout(self.rows)
        self.body.addStretch(1)

    def refresh(self) -> None:
        clear_layout(self.rows)
        games = self.store.games
        if self._filter:
            games = [game for game in games if game.system_key == self._filter]
        featured = self._featured(games)
        self.hero.set_game(featured)

        pool = [game for game in games if featured is None or game.id != featured.id]

        recent = sorted(
            (game for game in pool if game.last_played),
            key=lambda game: game.last_played,
            reverse=True,
        )[:8]
        if recent:
            self._add_row("Recientes", recent)
        for label, state_key in HOME_SHELVES:
            shelf = shelf_games(pool, state_key)
            if shelf:
                self._add_row(label, shelf)
        favorites = [game for game in pool if game.favorite][:8]
        if favorites:
            self._add_row("Favoritos", favorites)
        added = sorted(pool, key=lambda game: game.added_at, reverse=True)[:8]
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
        row.context_requested.connect(self.context_requested)
        self.rows.addWidget(row)


def _is_demo_game(game: Game) -> bool:
    return bool(re.search(r"\b(demo|playtest|play\s+test)\b", game.title or "", re.I))


class LibraryPage(QWidget):
    play_requested = Signal(object)
    details_requested = Signal(object)
    context_requested = Signal(object, object)
    add_requested = Signal()
    backdrop_change_requested = Signal(object)

    def __init__(self, store: Store, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self._filter = ""
        self._query = ""
        self._favorites_only = False
        self._favorites_filter = ""
        self._state_filter = ""
        self._inset_left = 0
        self._inset_top = 0
        self._hide_demos = bool(store.settings.get("hide_demos", False))
        self._view_mode = str(store.settings.get("library_view", "shelf"))
        if self._view_mode not in {"shelf", "grid"}:
            self._view_mode = "shelf"
        self._sort_key = str(store.settings.get("sort_key", "title"))
        self._sort_asc = bool(store.settings.get("sort_asc", True))
        if self._sort_key not in SORT_DEFAULT_ASC:
            self._sort_key = "title"

        header = QWidget(self)
        header.setObjectName("shelfHeader")
        self.header = header
        header_body = QVBoxLayout(header)
        header_body.setContentsMargins(32, 6, 32, 4)
        header_body.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.title_label = QLabel("Biblioteca")
        self.title_label.setObjectName("shelfWord")
        self.count_label = QLabel("")
        self.count_label.setObjectName("shelfCount")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.count_label)
        top_row.addLayout(title_box)
        top_row.addStretch(1)

        self.filters_button = QPushButton("Filtros  ▾")
        self.filters_button.setObjectName("filterBtn")
        self.filters_button.setCursor(Qt.PointingHandCursor)
        self.filters_button.setFocusPolicy(Qt.NoFocus)
        self._filters_menu = self._build_filters_menu()
        self.filters_button.setMenu(self._filters_menu)
        top_row.addWidget(self.filters_button, 0, Qt.AlignVCenter)
        header_body.addLayout(top_row)
        self._sync_filters_ui()

        self.canvas = ShelfCanvas(self)
        self.canvas.set_halo_enabled(bool(store.settings.get("shelf_halo", True)))
        self.canvas.activated.connect(self.play_requested)
        self.canvas.details_requested.connect(self.details_requested)
        self.canvas.context_requested.connect(self.context_requested)
        self.canvas.selection_changed.connect(self._on_selection)

        self.grid_scroll = QScrollArea(self)
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grid_scroll.setFrameShape(QFrame.NoFrame)
        grid_content = QWidget()
        grid_outer = QVBoxLayout(grid_content)
        grid_outer.setContentsMargins(38, 12, 38, 32)
        grid_outer.setSpacing(0)
        grid_wrap = QWidget()
        self.grid_layout = FlowLayout(grid_wrap, margin=0, h_spacing=18, v_spacing=22)
        grid_outer.addWidget(grid_wrap)
        grid_outer.addStretch(1)
        self.grid_scroll.setWidget(grid_content)
        self.grid_scroll.hide()

        self.info = QWidget(self)
        self.info.setObjectName("shelfInfo")
        info_body = QVBoxLayout(self.info)
        info_body.setContentsMargins(38, 8, 38, 8)
        info_body.setSpacing(4)
        self.info_title_row = QHBoxLayout()
        self.info_title_row.setContentsMargins(0, 0, 0, 0)
        self.info_title_row.setSpacing(10)
        self.info_emu_icon = QLabel("")
        self.info_emu_icon.setObjectName("shelfEmuIcon")
        self.info_emu_icon.setFixedSize(26, 26)
        self.info_emu_icon.setAlignment(Qt.AlignCenter)
        self.info_emu_icon.hide()
        self.info_title = QLabel("")
        self.info_title.setObjectName("shelfTitle")
        self.info_title.setAlignment(Qt.AlignCenter)
        self.info_title.setWordWrap(True)
        self.info_title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.info_title_row.addStretch(1)
        self.info_title_row.addWidget(self.info_emu_icon, 0, Qt.AlignVCenter)
        self.info_title_row.addWidget(self.info_title, 0, Qt.AlignVCenter)
        self.info_title_row.addStretch(1)
        self.info_meta = QLabel("")
        self.info_meta.setObjectName("shelfMeta")
        self.info_meta.setAlignment(Qt.AlignCenter)
        self.info_meta.setWordWrap(True)
        self.info_meta.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.info_actions = QHBoxLayout()
        self.info_actions.setSpacing(10)
        self.info_actions.setAlignment(Qt.AlignHCenter)
        self.play_button = QPushButton("Jugar ahora")
        self.play_button.setObjectName("primary")
        self.play_button.setCursor(Qt.PointingHandCursor)
        self.play_button.clicked.connect(self._play_current)
        self.info_actions.addWidget(self.play_button)
        info_body.addLayout(self.info_title_row)
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

        self.backdrop_button = QPushButton("Fondo  ▾", self)
        self.backdrop_button.setObjectName("filterBtn")
        self.backdrop_button.setCursor(Qt.PointingHandCursor)
        self.backdrop_button.setFocusPolicy(Qt.NoFocus)
        self._backdrop_menu = QMenu(self)
        self._backdrop_menu.aboutToShow.connect(self._populate_backdrop_menu)
        self.backdrop_button.setMenu(self._backdrop_menu)

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

    def set_chrome_insets(self, left: int, top: int) -> None:
        self._inset_left = max(0, int(left))
        self._inset_top = max(0, int(top))
        self.canvas.set_chrome_insets(self._inset_left, self._inset_top)
        self._layout_overlays()

    def _sync_info_title_height(self, inner_w: int) -> None:
        if not hasattr(self, "info_title"):
            return
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QFont, QFontMetrics

        icon_w = 36 if self.info_emu_icon.isVisible() else 0
        avail_w = max(240, inner_w - 64 - icon_w)
        self.info_title.setMinimumSize(0, 0)
        self.info_title.setMaximumSize(16777215, 16777215)

        style = active_style()
        measure_font = QFont(style.heading_font or "Cinzel")
        measure_font.setPixelSize(29)
        measure_font.setLetterSpacing(QFont.AbsoluteSpacing, 2.0)
        raw = self.info_title.text() or ""
        shown = raw.upper() if style.uppercase_headings else raw
        fm = QFontMetrics(measure_font)
        single_w = max(fm.horizontalAdvance(shown), fm.boundingRect(shown).width()) + 36
        target_w = min(avail_w, max(120, single_w))
        self.info_title.setFixedWidth(target_w)
        h_fm = fm.boundingRect(
            QRect(0, 0, target_w, 1000),
            Qt.AlignHCenter | Qt.TextWordWrap,
            shown,
        ).height()
        h_qlabel = self.info_title.heightForWidth(target_w)
        needed_h = max(h_qlabel, h_fm)
        if needed_h > 0:
            self.info_title.setFixedHeight(needed_h + 16)
        self.info_title.updateGeometry()

    def _layout_overlays(self) -> None:
        if not hasattr(self, "canvas"):
            return
        width = self.width()
        height = self.height()
        left = self._inset_left
        top = self._inset_top
        inner_w = max(0, width - left)
        inner_h = max(0, height - top)
        self.canvas.setGeometry(0, 0, width, height)
        header_h = self.header.sizeHint().height()
        self.header.setGeometry(left, top, inner_w, header_h)
        if hasattr(self, "grid_scroll"):
            self.grid_scroll.setGeometry(left, top + header_h, inner_w, max(0, inner_h - header_h))
        if not self.canvas._chrome_animating:
            self._sync_info_title_height(inner_w)
        bottom_h = self._bottom_height(inner_w)
        self.canvas.set_chrome_insets(left, top, bottom_h, header_h)
        self.bottom.setGeometry(left, height - bottom_h, inner_w, bottom_h)
        if self._view_mode == "grid" and hasattr(self, "grid_scroll"):
            self.grid_scroll.lower()
        else:
            self.canvas.lower()
        self.header.raise_()
        self.bottom.raise_()
        if hasattr(self, "backdrop_button"):
            show_bg_btn = self._view_mode == "shelf" and bool(self.canvas.items)
            self.backdrop_button.setVisible(show_bg_btn)
            if show_bg_btn:
                btn_sz = self.backdrop_button.sizeHint()
                self.backdrop_button.setGeometry(
                    max(left, width - btn_sz.width() - 28),
                    max(top, height - btn_sz.height() - 18),
                    btn_sz.width(),
                    btn_sz.height(),
                )
                self.backdrop_button.raise_()
        if hasattr(self, "_empty"):
            self._empty.setGeometry(left, top, inner_w, inner_h)
            if self._empty.isVisible():
                self._empty.raise_()

    def set_mode(self, favorites_only: bool) -> None:
        changed = self._favorites_only != favorites_only
        had_filter = bool(self._favorites_filter)
        self._favorites_only = favorites_only
        self._favorites_filter = ""
        self.title_label.setText("Favoritos" if favorites_only else "Biblioteca")
        if changed or had_filter or not self.canvas.items:
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

    def _build_filters_menu(self) -> QMenu:
        menu = QMenu(self)
        view_group = QActionGroup(menu)
        view_group.setExclusive(True)
        self._view_actions: dict[str, QAction] = {}
        for mode, label in (("shelf", "Vista: Estantería"), ("grid", "Vista: Cuadrícula")):
            act = QAction(label, menu, checkable=True)
            act.setChecked(self._view_mode == mode)
            act.triggered.connect(lambda _c, m=mode: self._set_view_mode(m))
            view_group.addAction(act)
            menu.addAction(act)
            self._view_actions[mode] = act

        menu.addSeparator()
        sort_menu = menu.addMenu("Ordenar por")
        sort_group = QActionGroup(sort_menu)
        sort_group.setExclusive(True)
        self._sort_actions: dict[str, QAction] = {}
        for key, label in SORT_OPTIONS:
            act = QAction(label, sort_menu, checkable=True)
            act.setChecked(self._sort_key == key)
            act.triggered.connect(lambda _c, k=key: self._set_sort_key(k))
            sort_group.addAction(act)
            sort_menu.addAction(act)
            self._sort_actions[key] = act

        self.order_action = QAction("", menu)
        self.order_action.triggered.connect(self._toggle_order)
        menu.addAction(self.order_action)

        state_menu = menu.addMenu("Estado")
        state_group = QActionGroup(state_menu)
        state_group.setExclusive(True)
        self._state_actions: dict[str, QAction] = {}
        for key, label in STATE_OPTIONS:
            act = QAction(label, state_menu, checkable=True)
            act.setChecked(self._state_filter == key)
            act.triggered.connect(lambda _c, k=key: self._set_state_filter(k))
            state_group.addAction(act)
            state_menu.addAction(act)
            self._state_actions[key] = act

        menu.addSeparator()
        self.hide_demos_action = QAction("Ocultar demos", menu, checkable=True)
        self.hide_demos_action.setChecked(self._hide_demos)
        self.hide_demos_action.toggled.connect(self._demos_toggled)
        menu.addAction(self.hide_demos_action)
        return menu

    def _set_sort_key(self, key: str) -> None:
        if not key:
            return
        self._sort_key = str(key)
        self._sort_asc = SORT_DEFAULT_ASC.get(self._sort_key, True)
        self._save_sort()
        self._sync_filters_ui()
        self.refresh(reset=True)

    def _toggle_order(self) -> None:
        self._sort_asc = not self._sort_asc
        self._save_sort()
        self._sync_filters_ui()
        self.refresh(reset=True)

    def _set_state_filter(self, key: str) -> None:
        self._state_filter = str(key or "")
        self._sync_filters_ui()
        self.refresh(reset=True)

    def _demos_toggled(self, checked: bool) -> None:
        self._hide_demos = bool(checked)
        self.store.settings["hide_demos"] = self._hide_demos
        self.store.save_settings()
        self._sync_filters_ui()
        self.refresh(reset=True)

    def _set_view_mode(self, mode: str) -> None:
        if mode not in {"shelf", "grid"}:
            return
        self._view_mode = mode
        self._sync_filters_ui()
        self.store.settings["library_view"] = mode
        self.store.save_settings()
        self.refresh()
        self.focus_canvas()

    def _save_sort(self) -> None:
        self.store.settings["sort_key"] = self._sort_key
        self.store.settings["sort_asc"] = self._sort_asc
        self.store.save_settings()

    def _sync_filters_ui(self) -> None:
        if hasattr(self, "order_action"):
            self.order_action.setText("Orden: ↑ Ascendente" if self._sort_asc else "Orden: ↓ Descendente")
        if hasattr(self, "_view_actions"):
            for mode, act in self._view_actions.items():
                act.setChecked(self._view_mode == mode)
        if hasattr(self, "_sort_actions"):
            for key, act in self._sort_actions.items():
                act.setChecked(self._sort_key == key)
        if hasattr(self, "_state_actions"):
            for key, act in self._state_actions.items():
                act.setChecked(self._state_filter == key)
        if hasattr(self, "filters_button"):
            active_badge = bool(self._state_filter or self._hide_demos)
            self.filters_button.setText("Filtros •  ▾" if active_badge else "Filtros  ▾")

    def _populate_backdrop_menu(self) -> None:
        menu = self._backdrop_menu
        menu.clear()
        game = self.canvas.current_game()
        if game is None:
            return

        dim_menu = menu.addMenu("Brillo / Oscuridad")
        dim_group = QActionGroup(dim_menu)
        dim_group.setExclusive(True)
        cur_dim = float(getattr(game, "backdrop_dim", 0.0) or 0.0)
        for label, val in (("Normal", 0.0), ("Oscuro", 0.30), ("Muy oscuro", 0.55)):
            act = QAction(label, dim_menu, checkable=True)
            act.setChecked(abs(cur_dim - val) < 0.05)
            act.triggered.connect(lambda _c, v=val: self._update_backdrop_setting(backdrop_dim=v))
            dim_group.addAction(act)
            dim_menu.addAction(act)

        blur_menu = menu.addMenu("Desenfoque")
        blur_group = QActionGroup(blur_menu)
        blur_group.setExclusive(True)
        cur_blur = int(getattr(game, "backdrop_blur", 0) or 0)
        for label, val in (("Nítido", 0), ("Suave", 6), ("Difuminado", 18)):
            act = QAction(label, blur_menu, checkable=True)
            act.setChecked(cur_blur == val)
            act.triggered.connect(lambda _c, v=val: self._update_backdrop_setting(backdrop_blur=v))
            blur_group.addAction(act)
            blur_menu.addAction(act)

        align_menu = menu.addMenu("Encuadre")
        align_group = QActionGroup(align_menu)
        align_group.setExclusive(True)
        cur_align = str(getattr(game, "backdrop_align", "center") or "center")
        for label, val in (("Arriba", "top"), ("Centro", "center"), ("Abajo", "bottom")):
            act = QAction(label, align_menu, checkable=True)
            act.setChecked(cur_align == val)
            act.triggered.connect(lambda _c, v=val: self._update_backdrop_setting(backdrop_align=v))
            align_group.addAction(act)
            align_menu.addAction(act)

        menu.addSeparator()
        pick_act = QAction("Cambiar fondo...", menu)
        pick_act.triggered.connect(lambda: self.backdrop_change_requested.emit(game))
        menu.addAction(pick_act)
        if game.backdrop:
            reset_act = QAction("Restaurar por defecto", menu)
            reset_act.triggered.connect(self._reset_current_backdrop)
            menu.addAction(reset_act)

    def _update_backdrop_setting(self, **kwargs) -> None:
        game = self.canvas.current_game()
        if game is None:
            return
        for key, value in kwargs.items():
            setattr(game, key, value)
        self.store.save_library()
        self.canvas._backdrop_cache.clear()
        self.canvas.update()

    def _reset_current_backdrop(self) -> None:
        game = self.canvas.current_game()
        if game is None:
            return
        game.backdrop = ""
        game.backdrop_dim = 0.0
        game.backdrop_blur = 0
        game.backdrop_align = "center"
        self.store.save_library()
        self.canvas._backdrop_cache.clear()
        self.canvas.update()

    def _visible_games(self) -> list[Game]:
        games = self.store.games
        if self._favorites_only:
            games = [game for game in games if game.favorite]
        active_filter = self.current_filter()
        if active_filter:
            games = [game for game in games if game.system_key == active_filter]
        if self._state_filter:
            games = [game for game in games if game.state == self._state_filter]
        if self._hide_demos:
            games = [game for game in games if not _is_demo_game(game)]
        query = self._query.strip().lower()
        if query:
            games = [
                game
                for game in games
                if query in game.title.lower()
                or query in game.subtitle.lower()
                or query in game.genre.lower()
                or query in game.system.lower()
                or query in game.emulator.lower()
                or query in game.notes.lower()
                or (game.year is not None and query in str(game.year))
            ]
        games = sorted(games, key=lambda game: game.title.lower())
        reverse = not self._sort_asc
        if self._sort_key == "played":
            present = sorted(
                (game for game in games if game.last_played),
                key=lambda game: game.last_played,
                reverse=reverse,
            )
            missing = [game for game in games if not game.last_played]
            games = present + missing
        elif self._sort_key == "hours":
            games.sort(key=lambda game: game.playtime_seconds, reverse=reverse)
        elif self._sort_key == "sessions":
            games.sort(key=lambda game: game.sessions, reverse=reverse)
        elif self._sort_key == "added":
            present = sorted(
                (game for game in games if game.added_at),
                key=lambda game: game.added_at,
                reverse=reverse,
            )
            missing = [game for game in games if not game.added_at]
            games = present + missing
        elif self._sort_key == "year":
            present = sorted(
                (game for game in games if game.year),
                key=lambda game: game.year or 0,
                reverse=reverse,
            )
            missing = [game for game in games if not game.year]
            games = present + missing
        else:
            games.sort(key=lambda game: game.title.lower(), reverse=reverse)
        return games

    def _on_selection(self, game: Game) -> None:
        badge = emulator_badge_pixmap(game, 26)
        if badge is not None and not badge.isNull():
            scaled = badge.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.info_emu_icon.setPixmap(scaled)
            self.info_emu_icon.setToolTip(game.emulator or game.system)
            self.info_emu_icon.show()
        else:
            self.info_emu_icon.clear()
            self.info_emu_icon.setToolTip("")
            self.info_emu_icon.hide()
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
            self.grid_scroll.hide()
            self.info.hide()
            self.bottom.hide()
            clear_layout(self.grid_layout)
            self._empty.show()
            self._layout_overlays()
            return
        self._empty.hide()
        if self._view_mode == "grid":
            self.canvas.hide()
            self.info.hide()
            self.bottom.hide()
            self.grid_scroll.show()
            clear_layout(self.grid_layout)
            for game in games:
                card = GameCard(game)
                card.play_requested.connect(self.play_requested)
                card.details_requested.connect(self.details_requested)
                card.context_requested.connect(self.context_requested)
                self.grid_layout.addWidget(card)
                card.show()
            self.grid_layout.parentWidget().updateGeometry()
            if reset:
                self.grid_scroll.verticalScrollBar().setValue(0)
        else:
            clear_layout(self.grid_layout)
            self.grid_scroll.hide()
            self.canvas.show()
            self.info.show()
            self.bottom.show()
            self.canvas.set_games(games)
            if reset:
                self.canvas.reset_position()
            game = self.canvas.current_game()
            if game is not None:
                self._on_selection(game)
        self._layout_overlays()

    def focus_canvas(self) -> None:
        target = self.grid_scroll if self._view_mode == "grid" else self.canvas
        target.setFocus(Qt.OtherFocusReason)


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
    add_folder_requested = Signal()

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

        profiles_by_key = {
            profile.key: profile for profile in all_profiles(self.store.settings)
        }
        for emulator in self.emulators:
            profile = profiles_by_key.get(emulator.key)
            if profile is not None and not profile.auto_scan:
                continue
            if emulator.key == "retroarch":
                continue
            if not any(game.system_key == emulator.system_key for game in self.store.games):
                issues.append(
                    (
                        "info",
                        emulator.name,
                        f"Emulador detectado, pero no hay juegos de {emulator.system} en las carpetas escaneadas.",
                        "__add_folder__",
                    )
                )

        for emulator in self.emulators:
            profile = profiles_by_key.get(emulator.key) or PROFILE_BY_KEY.get(emulator.key)
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

        dup_groups: dict[tuple[str, str, str], list[Game]] = {}
        for game in self.store.games:
            norm_title = re.sub(r"[^a-z0-9]+", " ", (game.title or "").lower()).strip()
            if not norm_title:
                continue
            key = (game.system_key, (game.emulator or "").strip().lower(), norm_title)
            dup_groups.setdefault(key, []).append(game)
        for group in dup_groups.values():
            if len(group) > 1:
                sample = group[0]
                issues.append(
                    (
                        "info",
                        f"Copias duplicadas: {sample.title}",
                        f"Hay {len(group)} entradas en {sample.system}"
                        + (f" ({sample.emulator})" if sample.emulator else "")
                        + ". Puedes ocultar la que sobre desde su ficha.",
                        None,
                    )
                )

        if not issues:
            self.body.addWidget(
                HealthRow("ok", "Todo en orden", "Los ejecutables y los archivos de tus juegos están en su sitio.")
            )
        else:
            for level, title_text, detail, action_target in issues:
                if isinstance(action_target, Game):
                    row = HealthRow(level, title_text, detail, "Reasignar")
                    row.action_clicked.connect(
                        lambda _checked=False, target=action_target: self.relink_requested.emit(target)
                    )
                    self.body.addWidget(row)
                elif action_target == "__add_folder__":
                    row = HealthRow(level, title_text, detail, "Añadir carpeta")
                    row.action_clicked.connect(self.add_folder_requested)
                    self.body.addWidget(row)
                else:
                    self.body.addWidget(HealthRow(level, title_text, detail))

        self.body.addWidget(SectionHeader("Emuladores y ports"))
        for emulator in self.emulators:
            level = "ok" if emulator.found else "warn"
            detail = emulator.executable if emulator.found else (emulator.note or "Sin ruta configurada.")
            self.body.addWidget(HealthRow(level, emulator.name, detail))

        self.body.addWidget(SectionHeader("Tiendas"))
        store_counts: dict[str, int] = {}
        for game in self.store.games:
            if game.source in {"steam", "epic", "gog"}:
                store_counts[game.source] = store_counts.get(game.source, 0) + 1
        for source_key, label, installed in store_statuses():
            count = store_counts.get(source_key, 0)
            active_store = installed or count > 0
            level = "ok" if active_store else "info"
            if count > 0:
                detail = f"Detectada · {count} juego" if count == 1 else f"Detectada · {count} juegos"
            elif installed:
                detail = "Detectada · sin juegos añadidos en la biblioteca"
            else:
                detail = "No detectada en este equipo"
            self.body.addWidget(HealthRow(level, label, detail))

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
    export_library = Signal()
    import_library = Signal()
    unhide_game_requested = Signal(str)
    unhide_path_requested = Signal(str)
    halo_changed = Signal(bool)
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
        self.update_downloading = False
        self.update_installing = False
        self.update_done_bytes = 0
        self.update_total_bytes = 0
        self.update_download_text = ""
        self.update_error = ""
        self.update_message = ""
        self._update_install_btn: Optional[QPushButton] = None
        self._update_later_btn: Optional[QPushButton] = None
        self._update_status_note: Optional[QLabel] = None
        self._update_progress_bar: Optional[QProgressBar] = None
        self._active_tab = "emulators"
        self._tab_buttons: dict[str, QPushButton] = {}
        self._tab_indices: dict[str, int] = {}
        self._stack: Optional[QStackedWidget] = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.body = _scroll_page()
        outer.addWidget(scroll)

    def set_emulators(self, emulators: list[Emulator]) -> None:
        self.emulators = emulators

    def set_profiles(self, profiles: list[EmulatorProfile]) -> None:
        self.profiles = profiles

    def set_section(self, key: str) -> None:
        if key not in self._tab_indices:
            return
        self._active_tab = key
        for tab_key, button in self._tab_buttons.items():
            button.setChecked(tab_key == key)
        if self._stack is not None:
            self._stack.setCurrentIndex(self._tab_indices[key])

    def refresh(self) -> None:
        clear_layout(self.body)
        self._tab_buttons.clear()
        self._tab_indices.clear()
        self._update_install_btn = None
        self._update_later_btn = None
        self._update_status_note = None
        self._update_progress_bar = None

        title = QLabel("Ajustes")
        title.setObjectName("h2")
        self.body.addWidget(title)

        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(8)
        style = active_style()
        tab_style = (
            "QPushButton {"
            " padding: 8px 16px;"
            " border-radius: 8px;"
            " background: rgba(255, 255, 255, 0.05);"
            " border: 1px solid rgba(255, 255, 255, 0.09);"
            f" color: {style.muted};"
            " font-weight: 600;"
            "}"
            "QPushButton:hover {"
            " background: rgba(255, 255, 255, 0.09);"
            f" color: {style.text};"
            "}"
            "QPushButton:checked {"
            f" background: {style.accent};"
            f" border-color: {style.accent};"
            f" color: {style.bg};"
            " font-weight: 700;"
            "}"
        )
        for key, label in (
            ("emulators", "Emuladores"),
            ("library", "Biblioteca"),
            ("appearance", "Apariencia"),
            ("maintenance", "Mantenimiento"),
        ):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == self._active_tab)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(tab_style)
            btn.clicked.connect(lambda _checked=False, k=key: self.set_section(k))
            self._tab_buttons[key] = btn
            tabs_row.addWidget(btn)
        tabs_row.addStretch(1)
        self.body.addLayout(tabs_row)

        stack = QStackedWidget()
        self._stack = stack
        builders = (
            ("emulators", self._build_emulators_tab()),
            ("library", self._build_library_tab()),
            ("appearance", self._build_appearance_tab()),
            ("maintenance", self._build_maintenance_tab()),
        )
        for idx, (key, page_widget) in enumerate(builders):
            stack.addWidget(page_widget)
            self._tab_indices[key] = idx
        stack.setCurrentIndex(self._tab_indices.get(self._active_tab, 0))
        self.body.addWidget(stack, 1)

    def _make_tab_container(self) -> tuple[QWidget, QVBoxLayout]:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(12)
        return container, layout

    def _build_emulators_tab(self) -> QWidget:
        container, layout = self._make_tab_container()
        layout.addWidget(SectionHeader("Emuladores y ports"))
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
            layout.addWidget(frame)

        if not self.emulators:
            hint = QLabel("No hay emuladores detectados. Puedes indicar la ruta de cada uno a mano.")
            hint.setObjectName("tiny")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        manage = QPushButton("Añadir o detectar emulador")
        manage.setObjectName("ghost")
        manage.setCursor(Qt.PointingHandCursor)
        manage.clicked.connect(self.manage_emulators)
        layout.addWidget(manage, 0, Qt.AlignLeft)

        layout.addWidget(SectionHeader("Compatibles por consola"))
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
            layout.addWidget(frame)
        if not self.profiles:
            hint = QLabel("Sin perfiles compatibles todavía.")
            hint.setObjectName("tiny")
            layout.addWidget(hint)
        layout.addStretch(1)
        return container

    def _build_library_tab(self) -> QWidget:
        container, layout = self._make_tab_container()
        layout.addWidget(SectionHeader("Carpetas escaneadas"))
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
            layout.addWidget(frame)
        add_folder = QPushButton("Añadir carpeta")
        add_folder.setObjectName("ghost")
        add_folder.setCursor(Qt.PointingHandCursor)
        add_folder.clicked.connect(self._add_folder)
        layout.addWidget(add_folder, 0, Qt.AlignLeft)
        if not folders:
            hint = QLabel(
                "Sin carpetas propias: Umbral revisa Descargas, Escritorio, Documentos y Juegos."
            )
            hint.setObjectName("tiny")
            hint.setWordWrap(True)
            layout.addWidget(hint)

        layout.addWidget(SectionHeader("Juegos de PC"))
        pc_text = QLabel(
            "Umbral busca ejecutables de PC en tus carpetas y comprueba el nombre en Steam, "
            "itch.io y PCGamingWiki antes de proponerlos. También detecta descargas recientes "
            "de ROMs y te avisa si falta el emulador."
        )
        pc_text.setObjectName("muted")
        pc_text.setWordWrap(True)
        layout.addWidget(pc_text)
        steam_check = QCheckBox("No proponer juegos que ya estén instalados en Steam")
        steam_check.setChecked(bool(self.store.settings.get("steam_scrape", True)))
        steam_check.toggled.connect(self._toggle_steam)
        layout.addWidget(steam_check)
        scan_pc = QPushButton("Buscar juegos de PC")
        scan_pc.setObjectName("ghost")
        scan_pc.setCursor(Qt.PointingHandCursor)
        scan_pc.clicked.connect(self.scan_pc_requested)
        layout.addWidget(scan_pc, 0, Qt.AlignLeft)
        layout.addStretch(1)
        return container

    def _build_appearance_tab(self) -> QWidget:
        from PySide6.QtWidgets import QColorDialog

        from .style import STYLES
        from .theme import ACCENTS
        from .widgets import StylePreview

        container, layout = self._make_tab_container()
        layout.addWidget(SectionHeader("Estilo visual"))
        current_style = active_style().key
        styles_grid = QGridLayout()
        styles_grid.setSpacing(12)
        for index, style in enumerate(STYLES):
            card = StylePreview(style, selected=(style.key == current_style))
            card.clicked.connect(self.style_changed.emit)
            styles_grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(styles_grid)

        layout.addWidget(SectionHeader("Color de acento"))
        accent_row = QHBoxLayout()
        accent_row.setSpacing(10)
        current_accent = str(self.store.settings.get("accent") or active_style().accent).lower()
        for label, color in ACCENTS:
            swatch = QPushButton("")
            swatch.setToolTip(label)
            swatch.setFixedSize(28, 28)
            swatch.setCursor(Qt.PointingHandCursor)
            selected = color.lower() == current_accent
            ring = f"2px solid {active_style().accent_2}" if selected else "1px solid rgba(255, 255, 255, 0.25)"
            swatch.setStyleSheet(
                f"QPushButton {{ background: {color}; border: {ring}; border-radius: 14px; }}"
                "QPushButton:hover { border: 2px solid #ffffff; }"
            )
            swatch.clicked.connect(lambda _checked=False, c=color: self.accent_changed.emit(c))
            accent_row.addWidget(swatch)

        def _pick_custom_accent() -> None:
            from PySide6.QtGui import QColor

            chosen = QColorDialog.getColor(QColor(current_accent), self, "Elegir color de acento")
            if chosen.isValid():
                self.accent_changed.emit(chosen.name())

        custom_btn = QPushButton("Personalizar…")
        custom_btn.setObjectName("ghost")
        custom_btn.setCursor(Qt.PointingHandCursor)
        custom_btn.clicked.connect(_pick_custom_accent)
        accent_row.addWidget(custom_btn)
        accent_row.addStretch(1)
        layout.addLayout(accent_row)

        layout.addWidget(SectionHeader("Carátulas"))
        covers_text = QLabel(
            "Umbral descarga la carátula oficial de cada juego desde IGDB, Steam o itch.io. "
            "Si un juego aparece con un monograma, aún no tiene carátula."
        )
        covers_text.setObjectName("muted")
        covers_text.setWordWrap(True)
        layout.addWidget(covers_text)
        covers_button = QPushButton("Buscar carátulas de nuevo")
        covers_button.setObjectName("ghost")
        covers_button.setCursor(Qt.PointingHandCursor)
        covers_button.clicked.connect(self.covers_requested)
        layout.addWidget(covers_button, 0, Qt.AlignLeft)

        layout.addWidget(SectionHeader("Estantería 3D"))
        halo_check = QCheckBox("Mostrar halo de color alrededor de los juegos en la Estantería 3D")
        halo_check.setChecked(bool(self.store.settings.get("shelf_halo", True)))
        halo_check.toggled.connect(self._toggle_halo)
        self.halo_check = halo_check
        layout.addWidget(halo_check)
        layout.addStretch(1)
        return container

    def _build_maintenance_tab(self) -> QWidget:
        container, layout = self._make_tab_container()
        layout.addWidget(SectionHeader("Juegos ocultos"))
        hidden_ids = [str(item) for item in self.store.settings.get("hidden_games", []) if str(item)]
        hidden_paths = [str(item) for item in self.store.settings.get("hidden_paths", []) if str(item)]
        if not hidden_ids and not hidden_paths:
            empty_hidden = QLabel("No hay juegos ocultos.")
            empty_hidden.setObjectName("tiny")
            layout.addWidget(empty_hidden)
        else:
            for game_id in hidden_ids:
                frame = QFrame()
                frame.setObjectName("tile")
                row = QHBoxLayout(frame)
                row.setContentsMargins(16, 10, 16, 10)
                row.setSpacing(12)
                label = QLabel(game_id)
                label.setObjectName("muted")
                label.setWordWrap(True)
                row.addWidget(label, 1)
                restore = QPushButton("Restaurar")
                restore.setObjectName("icon")
                restore.setCursor(Qt.PointingHandCursor)
                restore.clicked.connect(
                    lambda _checked=False, value=game_id: self.unhide_game_requested.emit(value)
                )
                row.addWidget(restore)
                layout.addWidget(frame)
            for path_value in hidden_paths:
                frame = QFrame()
                frame.setObjectName("tile")
                row = QHBoxLayout(frame)
                row.setContentsMargins(16, 10, 16, 10)
                row.setSpacing(12)
                label = QLabel(f"{Path(path_value).name}  ·  {path_value}")
                label.setObjectName("muted")
                label.setWordWrap(True)
                row.addWidget(label, 1)
                restore = QPushButton("Restaurar")
                restore.setObjectName("icon")
                restore.setCursor(Qt.PointingHandCursor)
                restore.clicked.connect(
                    lambda _checked=False, value=path_value: self.unhide_path_requested.emit(value)
                )
                row.addWidget(restore)
                layout.addWidget(frame)

        layout.addWidget(SectionHeader("Datos y mantenimiento"))
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
        export_lib = QPushButton("Exportar biblioteca")
        export_lib.setObjectName("ghost")
        export_lib.setCursor(Qt.PointingHandCursor)
        export_lib.clicked.connect(self.export_library)
        import_lib = QPushButton("Importar biblioteca")
        import_lib.setObjectName("ghost")
        import_lib.setCursor(Qt.PointingHandCursor)
        import_lib.clicked.connect(self.import_library)
        data_row.addWidget(open_data)
        data_row.addWidget(rescan)
        data_row.addWidget(export)
        data_row.addWidget(export_lib)
        data_row.addWidget(import_lib)
        data_row.addStretch(1)
        layout.addLayout(data_row)
        note = QLabel(
            "Umbral no mueve tus ROMs ni tus partidas. Solo guarda rutas, tiempos de juego y preferencias."
        )
        note.setObjectName("tiny")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return container

    def _open_release_page(self) -> None:
        if (
            self.available_update is not None
            and self.available_update.page_url.startswith("https://github.com/")
        ):
            QDesktopServices.openUrl(QUrl(self.available_update.page_url))

    def set_update_checking(self, checking: bool) -> None:
        self.update_checking = checking
        if checking:
            self.update_message = "Comprobando en GitHub…"
        self.refresh()

    def set_update_available(self, info: UpdateInfo) -> None:
        self.available_update = info
        self.update_checking = False
        self.update_downloading = False
        self.update_installing = False
        self.update_done_bytes = 0
        self.update_total_bytes = 0
        self.update_download_text = ""
        self.update_error = ""
        self.update_message = ""
        self.refresh()

    def set_update_downloading(self, done: int, total: int) -> None:
        self.update_downloading = True
        self.update_installing = False
        self.update_done_bytes = done
        self.update_total_bytes = total
        self.update_error = ""
        if self._update_progress_bar is not None:
            progress_text = apply_download_progress(self._update_progress_bar, done, total)
            self._update_progress_bar.setVisible(True)
        elif total > 0:
            from ..updater import format_download_progress

            progress_text = format_download_progress(done, total)
        elif done > 0:
            from ..updater import format_download_progress

            progress_text = format_download_progress(done, total)
        else:
            progress_text = "Solicitud recibida · conectando con GitHub…"
        if total > 0:
            percent = min(100, int(done * 100 / total))
            self.update_download_text = f"Descargando actualización: {progress_text}"
            btn_label = f"Descargando {percent} %…"
        elif done > 0:
            self.update_download_text = f"Descargando actualización: {progress_text}"
            btn_label = "Descargando…"
        else:
            self.update_download_text = progress_text
            btn_label = "Conectando…"
        if self._update_install_btn is not None:
            self._update_install_btn.setText(btn_label)
            self._update_install_btn.setEnabled(False)
        if self._update_later_btn is not None:
            self._update_later_btn.setEnabled(False)
        if self._update_status_note is not None:
            self._update_status_note.setText(self.update_download_text)
            self._update_status_note.setVisible(True)

    def set_update_installing(self) -> None:
        self.update_downloading = False
        self.update_installing = True
        self.update_error = ""
        self.update_download_text = (
            "Descarga completada · cerrando Umbral para instalar y reiniciar…"
        )
        if self._update_progress_bar is not None:
            self._update_progress_bar.setRange(0, 100)
            self._update_progress_bar.setValue(100)
            self._update_progress_bar.setVisible(True)
        if self._update_install_btn is not None:
            self._update_install_btn.setText("Instalando…")
            self._update_install_btn.setEnabled(False)
        if self._update_later_btn is not None:
            self._update_later_btn.setEnabled(False)
        if self._update_status_note is not None:
            self._update_status_note.setText(self.update_download_text)
            self._update_status_note.setVisible(True)

    def set_update_error(self, message: str) -> None:
        self.update_downloading = False
        self.update_installing = False
        self.update_done_bytes = 0
        self.update_total_bytes = 0
        self.update_download_text = ""
        self.update_error = message
        if self._update_progress_bar is not None:
            self._update_progress_bar.setVisible(False)
        if self._update_install_btn is not None:
            self._update_install_btn.setText("Reintentar")
            self._update_install_btn.setEnabled(True)
        if self._update_later_btn is not None:
            self._update_later_btn.setEnabled(True)
        if self._update_status_note is not None:
            self._update_status_note.setText(message)
            self._update_status_note.setVisible(True)

    def set_update_result(self, message: str) -> None:
        self.update_checking = False
        self.update_message = message
        self.refresh()

    def dismiss_update(self) -> None:
        version = self.available_update.version if self.available_update is not None else ""
        self.available_update = None
        self.update_downloading = False
        self.update_installing = False
        self.update_done_bytes = 0
        self.update_total_bytes = 0
        self.update_download_text = ""
        self.update_error = ""
        if version:
            self.update_message = (
                f"Versión {version} aplazada. Puedes comprobarla de nuevo cuando quieras."
            )
        else:
            self.update_message = (
                "Actualización aplazada. Puedes comprobarla de nuevo cuando quieras."
            )
        self.refresh()

    def _browse_executable(self, key: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona el ejecutable", "", executable_file_filter()
        )
        if path:
            self.store.settings.setdefault("emulator_paths", {})[key] = path
            self.store.save_settings()
            self.rescan_requested.emit()

    def _toggle_steam(self, checked: bool) -> None:
        self.store.settings["steam_scrape"] = bool(checked)
        self.store.save_settings()

    def _toggle_halo(self, checked: bool) -> None:
        self.store.settings["shelf_halo"] = bool(checked)
        self.store.save_settings()
        self.halo_changed.emit(bool(checked))

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
