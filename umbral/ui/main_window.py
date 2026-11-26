from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, QUrl, QVariantAnimation
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..cover_worker import CoverWorker
from ..covers import clear_cover_cache, cover_needs_refresh, game_cover
from .. import __version__
from ..consoles import CONSOLE_EXTENSIONS
from ..detect import DETECTION_VERSION, working_dir_for
from ..downloads import Download, emulator_for, mark_seen
from ..launcher import LaunchError, ProcessWatcher, SteamWatcher, diagnostic_text, launch_game, steam_app_id, validate
from ..models import Emulator, Game, now_iso, slugify
from ..paths import assets_dir, data_dir, executable_file_filter, path_key as _path_key
from ..relink import missing_parts, relink, relocate_missing_paths
from ..scan import DetectWorker, ScanWorker
from ..standalone import StandaloneCandidate
from ..store import Store
from ..profiles import EmulatorProfile, all_profiles, custom_profiles
from ..updater import UpdateError, UpdateInfo, apply_update, backup_data, is_newer
from .dialogs import (
    AddGameDialog,
    EmulatorChoiceDialog,
    EmulatorSetupDialog,
    GameDetailDialog,
    GameScanDialog,
)
from .gamepad import GamepadWatcher
from .icons import vector_icon
from .pages import HealthPage, HomePage, LibraryPage, SettingsPage, StatsPage, clear_layout
from .shelf import apply_style
from .style import active, is_dark, is_reduced_motion, set_active, set_reduced_motion
from .theme import qss
from .update_dialog import CheckWorker, DownloadWorker
from .widgets import Backdrop, StartupOverlay, Toast, UmbralButton, UpdateBanner


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.store = Store()
        self.emulators: list[Emulator] = []
        self.watchers: list[ProcessWatcher] = []
        self.scan_worker: Optional[ScanWorker] = None
        self.detect_worker: Optional[DetectWorker] = None
        self.cover_worker: Optional[CoverWorker] = None
        self.update_worker: Optional[CheckWorker] = None
        self.download_worker: Optional[DownloadWorker] = None
        self.update_info = None
        self._current_page_key = "library"
        self._updating = False
        self._closing = False
        self._detect_announce = False
        self._prune_after_detect = False
        self._fullscreen_mode = False
        self._pre_fullscreen_collapsed = False
        style_key = str(self.store.settings.get("style", "souls"))
        set_active(style_key)
        set_reduced_motion(bool(self.store.settings.get("reduce_animations", False)))
        apply_style(style_key)
        self.setWindowTitle("Umbral")
        self.setMinimumSize(1040, 660)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = max(1040, min(1420, available.width() - 40))
            height = max(660, min(900, available.height() - 40))
            self.resize(width, height)
            self.move(
                available.x() + (available.width() - width) // 2,
                available.y() + (available.height() - height) // 2,
            )
        else:
            self.resize(1420, 900)
        icon_path = assets_dir() / "umbral.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build()
        self._apply_theme()
        self._navigate("library")
        QTimer.singleShot(80, self._bootstrap)

    def _build(self) -> None:
        root = Backdrop()
        self.backdrop = root
        root.setObjectName("root")
        self._sidebar_expanded_width = 238
        self._sidebar_width = self._sidebar_expanded_width
        self._sidebar_collapsed = False
        self._sidebar_anim = QVariantAnimation(self)
        self._sidebar_anim.setDuration(260)
        self._sidebar_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._sidebar_anim.valueChanged.connect(self._apply_sidebar_width)
        self._sidebar_anim.finished.connect(self._on_sidebar_anim_finished)
        self._topbar_height = 84
        self._systems_signature: tuple = ()
        self._system_buttons: dict[str, QPushButton] = {}

        self.stack = QStackedWidget(root)

        sidebar = QFrame(root)
        sidebar.setObjectName("sidebar")
        sidebar.setFocusPolicy(Qt.NoFocus)
        self.sidebar = sidebar
        sidebar_shell = QVBoxLayout(sidebar)
        sidebar_shell.setContentsMargins(0, 0, 0, 0)
        sidebar_shell.setSpacing(0)
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setObjectName("sidebarScroll")
        sidebar_scroll.setFocusPolicy(Qt.NoFocus)
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setFrameShape(QFrame.NoFrame)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_scroll.viewport().setAutoFillBackground(False)
        sidebar_scroll.viewport().setFocusPolicy(Qt.NoFocus)
        side_content = QWidget()
        side_content.setObjectName("sidebarContent")
        side_content.setFocusPolicy(Qt.NoFocus)
        side_content.setAutoFillBackground(False)
        self._side_content = side_content
        side = QVBoxLayout(side_content)
        side.setContentsMargins(18, 22, 18, 18)
        side.setSpacing(6)
        sidebar_scroll.setWidget(side_content)
        sidebar_shell.addWidget(sidebar_scroll)

        self._nav_indicator = QFrame(side_content)
        self._nav_indicator.setObjectName("navIndicator")
        self._nav_indicator.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._nav_indicator.hide()
        self._nav_anim = QPropertyAnimation(self._nav_indicator, b"geometry", self)
        self._nav_anim.setDuration(190)
        self._nav_anim.setEasingCurve(QEasingCurve.OutCubic)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        logo = QLabel()
        icon_path = assets_dir() / "umbral.svg"
        if icon_path.exists():
            logo.setPixmap(
                QPixmap(str(icon_path)).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        brand_row.addWidget(logo)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        name = QLabel("UMBRAL")
        name.setObjectName("brandName")
        tagline = QLabel("ARCHIVO DE JUEGOS")
        tagline.setObjectName("tiny")
        brand_text.addWidget(name)
        brand_text.addWidget(tagline)
        brand_row.addLayout(brand_text)
        brand_row.addStretch(1)
        side.addLayout(brand_row)
        side.addSpacing(20)

        self.nav_buttons: dict[str, QPushButton] = {}
        for key, label in (
            ("home", "Inicio"),
            ("library", "Biblioteca"),
            ("favorites", "Favoritos"),
            ("stats", "Estadísticas"),
            ("health", "Salud"),
        ):
            button = QPushButton(label)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.NoFocus)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, value=key: self._navigate(value))
            self.nav_buttons[key] = button
            side.addWidget(button)

        side.addSpacing(16)
        self.systems_section = QWidget()
        systems_layout = QVBoxLayout(self.systems_section)
        systems_layout.setContentsMargins(0, 0, 0, 0)
        systems_layout.setSpacing(1)
        systems_label = QLabel("SISTEMAS")
        systems_label.setObjectName("tiny")
        systems_label.setStyleSheet("font-weight: 700;")
        systems_layout.addWidget(systems_label)
        self._systems_container = QWidget()
        self.systems_box = QVBoxLayout(self._systems_container)
        self.systems_box.setContentsMargins(0, 0, 0, 0)
        self.systems_box.setSpacing(1)
        self._sys_indicator = QFrame(self._systems_container)
        self._sys_indicator.setObjectName("sysIndicator")
        self._sys_indicator.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._sys_indicator.hide()
        self._sys_anim = QPropertyAnimation(self._sys_indicator, b"geometry", self)
        self._sys_anim.setDuration(170)
        self._sys_anim.setEasingCurve(QEasingCurve.OutCubic)
        systems_layout.addWidget(self._systems_container)
        side.addWidget(self.systems_section)

        side.addSpacing(12)
        self.collections_section = QWidget()
        collections_layout = QVBoxLayout(self.collections_section)
        collections_layout.setContentsMargins(0, 0, 0, 0)
        collections_layout.setSpacing(1)
        col_header = QHBoxLayout()
        col_header.setContentsMargins(0, 0, 0, 0)
        collections_label = QLabel("COLECCIONES")
        collections_label.setObjectName("tiny")
        collections_label.setStyleSheet("font-weight: 700;")
        col_header.addWidget(collections_label)
        col_header.addStretch(1)
        new_col_btn = QPushButton("＋")
        new_col_btn.setObjectName("icon")
        new_col_btn.setFixedSize(22, 22)
        new_col_btn.setFocusPolicy(Qt.NoFocus)
        new_col_btn.setCursor(Qt.PointingHandCursor)
        new_col_btn.setToolTip("Crear colección")
        new_col_btn.clicked.connect(self._create_collection_prompt)
        col_header.addWidget(new_col_btn)
        collections_layout.addLayout(col_header)
        self.collections_box = QVBoxLayout()
        self.collections_box.setContentsMargins(0, 0, 0, 0)
        self.collections_box.setSpacing(1)
        self._collection_buttons: dict[str, QPushButton] = {}
        collections_layout.addLayout(self.collections_box)
        side.addWidget(self.collections_section)

        side.addStretch(1)
        divider = QFrame()
        divider.setObjectName("divider")
        side.addWidget(divider)
        settings_button = QPushButton("Ajustes")
        settings_button.setObjectName("nav")
        settings_button.setCheckable(True)
        settings_button.setFocusPolicy(Qt.NoFocus)
        settings_button.setCursor(Qt.PointingHandCursor)
        settings_button.clicked.connect(lambda: self._navigate("settings"))
        self.nav_buttons["settings"] = settings_button
        side.addWidget(settings_button)
        self.update_button = QPushButton("Buscar actualizaciones")
        self.update_button.setObjectName("nav")
        self.update_button.setFocusPolicy(Qt.NoFocus)
        self.update_button.setCursor(Qt.PointingHandCursor)
        self.update_button.clicked.connect(lambda: self._check_updates(manual=True))
        side.addWidget(self.update_button)
        self.version_label = QLabel(f"v{__version__} · biblioteca local")
        self.version_label.setObjectName("tiny")
        side.addWidget(self.version_label)
        credit = QLabel("Un proyecto de Gonzalo Sanjurjo")
        credit.setObjectName("tiny")
        credit.setWordWrap(True)
        credit.setStyleSheet(f"color: {active().accent_2};")
        side.addWidget(credit)

        topbar = QFrame(root)
        topbar.setObjectName("topbar")
        self.topbar = topbar
        top = QHBoxLayout(topbar)
        top.setContentsMargins(24, 18, 32, 10)
        top.setSpacing(12)
        self.sidebar_toggle = UmbralButton("", icon_name="chevron_left", icon_size=16)
        self.sidebar_toggle.setObjectName("sidebarToggle")
        self.sidebar_toggle.setFixedSize(36, 36)
        self.sidebar_toggle.setFocusPolicy(Qt.NoFocus)
        self.sidebar_toggle.setCursor(Qt.PointingHandCursor)
        self.sidebar_toggle.setToolTip("Ocultar barra lateral")
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        top.addWidget(self.sidebar_toggle)
        self.search = QLineEdit()
        self.search.setObjectName("searchInput")
        self.search.setPlaceholderText("Buscar en tu biblioteca...")
        self.search.setMinimumWidth(190)
        self.search.setMaximumWidth(320)
        self._search_icon_action = QAction(vector_icon("search", active().muted, 14), "", self.search)
        self.search.addAction(self._search_icon_action, QLineEdit.LeadingPosition)
        self._search_clear_action = QAction(vector_icon("close", active().muted, 13), "Limpiar", self.search)
        self._search_clear_action.triggered.connect(self.search.clear)
        self._search_clear_action.setVisible(False)
        self.search.addAction(self._search_clear_action, QLineEdit.TrailingPosition)
        self.search.textChanged.connect(self._search)
        top.addWidget(self.search, 1)
        top.addStretch(1)
        self.add_button = UmbralButton("Añadir juego", icon_name="plus", icon_size=14)
        self.add_button.setObjectName("primary")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self._add_game)
        top.addWidget(self.add_button)
        self.scan_button = UmbralButton("Buscar juegos", icon_name="search", icon_size=14)
        self.scan_button.setObjectName("ghost")
        self.scan_button.setCursor(Qt.PointingHandCursor)
        self.scan_button.clicked.connect(self._scan_pc_games)
        top.addWidget(self.scan_button)
        self.refresh_button = UmbralButton("Refrescar rutas", icon_name="refresh", icon_size=14)
        self.refresh_button.setObjectName("ghost")
        self.refresh_button.setCursor(Qt.PointingHandCursor)
        self.refresh_button.setToolTip(
            "Actualiza las rutas de tu biblioteca y quita los juegos que ya no existan."
        )
        self.refresh_button.clicked.connect(self._refresh_paths)
        top.addWidget(self.refresh_button)
        self.fullscreen_button = UmbralButton("", icon_name="fullscreen", icon_size=15)
        self.fullscreen_button.setObjectName("sidebarToggle")
        self.fullscreen_button.setFixedSize(36, 36)
        self.fullscreen_button.setFocusPolicy(Qt.NoFocus)
        self.fullscreen_button.setCursor(Qt.PointingHandCursor)
        self.fullscreen_button.setToolTip("Modo Pantalla Completa / Mando (F11)")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen_mode)
        top.addWidget(self.fullscreen_button)

        self.home = HomePage(self.store)
        self.library = LibraryPage(self.store)
        self.stats = StatsPage(self.store)
        self.health = HealthPage(self.store)
        self.settings_page = SettingsPage(self.store)
        for padded_page in (self.home, self.stats, self.health, self.settings_page):
            padded_page.setContentsMargins(self._sidebar_width, self._topbar_height, 0, 0)
        self.library.set_chrome_insets(self._sidebar_width, self._topbar_height)

        for page in (self.home, self.library):
            page.play_requested.connect(self._play)
            page.details_requested.connect(self._details)
            page.context_requested.connect(self._show_game_menu)
            page.add_requested.connect(self._add_game)
        self.library.backdrop_change_requested.connect(self._pick_game_backdrop)
        self.health.rescan_requested.connect(self._rescan)
        self.health.relink_requested.connect(self._relink_game)
        self.health.add_folder_requested.connect(self._add_scan_folder)
        self.settings_page.rescan_requested.connect(self._rescan)
        self.settings_page.scan_pc_requested.connect(self._scan_pc_games)
        self.settings_page.covers_requested.connect(self._refresh_covers)
        self.settings_page.manage_emulators.connect(self._manage_emulators)
        self.settings_page.accent_changed.connect(self._set_accent)
        self.settings_page.style_changed.connect(self._set_style)
        self.settings_page.halo_changed.connect(self._set_halo)
        self.settings_page.reduce_animations_changed.connect(self._set_reduced_motion)
        self.settings_page.open_data.connect(self._open_data)
        self.settings_page.export_diagnostics.connect(self._export_diagnostics)
        self.settings_page.export_library.connect(self._export_library)
        self.settings_page.import_library.connect(self._import_library)
        self.settings_page.unhide_game_requested.connect(self._unhide_game)
        self.settings_page.unhide_path_requested.connect(self._unhide_path)
        self.settings_page.check_updates.connect(lambda: self._check_updates(manual=True))
        self.settings_page.install_update.connect(self._install_update)
        self.settings_page.later_update.connect(self._postpone_update)

        self.pages = {
            "home": self.home,
            "library": self.library,
            "stats": self.stats,
            "health": self.health,
            "settings": self.settings_page,
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        self.setCentralWidget(root)
        self.sidebar.raise_()
        self.topbar.raise_()

        self.toast = Toast(self)
        self.update_banner = UpdateBanner(self)
        self.update_banner.install_clicked.connect(self._install_update)
        self.update_banner.postpone_clicked.connect(self._postpone_update)
        self._startup_overlay: Optional[StartupOverlay] = None
        self._manual_covers_scan = False
        if os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen":
            self._startup_overlay = StartupOverlay(self)
            self._startup_overlay.start()
        self._layout_chrome()

        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(self._focus_search)
        rescan_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        rescan_shortcut.activated.connect(self._rescan)
        fullscreen_shortcut = QShortcut(QKeySequence("F11"), self)
        fullscreen_shortcut.activated.connect(self.toggle_fullscreen_mode)
        esc_shortcut = QShortcut(QKeySequence("Escape"), self)
        esc_shortcut.activated.connect(self._exit_fullscreen_if_active)

        self._gamepad_bar = QFrame(root)
        self._gamepad_bar.setObjectName("gamepadBar")
        gp_row = QHBoxLayout(self._gamepad_bar)
        gp_row.setContentsMargins(16, 6, 12, 6)
        gp_row.setSpacing(14)
        gp_hint = QLabel(
            "A Jugar   ·   X Girar caja   ·   Y Favorito   ·   LB / RB Sistema   ·   I Ficha   ·   Start / F11 Salir"
        )
        gp_hint.setObjectName("gamepadHint")
        gp_row.addWidget(gp_hint)
        gp_exit = QPushButton("Salir (F11)")
        gp_exit.setObjectName("icon")
        gp_exit.setCursor(Qt.PointingHandCursor)
        gp_exit.clicked.connect(self.toggle_fullscreen_mode)
        gp_row.addWidget(gp_exit)
        self._gamepad_bar.hide()

        self.gamepad = GamepadWatcher(self)
        self.gamepad.navigate_left.connect(self._gamepad_left)
        self.gamepad.navigate_right.connect(self._gamepad_right)
        self.gamepad.navigate_up.connect(self._gamepad_up)
        self.gamepad.navigate_down.connect(self._gamepad_down)
        self.gamepad.confirm.connect(self._gamepad_confirm)
        self.gamepad.back.connect(self._gamepad_back)
        self.gamepad.flip_requested.connect(self._gamepad_flip)
        self.gamepad.favorite_requested.connect(self._gamepad_favorite)
        self.gamepad.prev_system.connect(lambda: self._gamepad_cycle_system(-1))
        self.gamepad.next_system.connect(lambda: self._gamepad_cycle_system(1))
        self.gamepad.fullscreen_requested.connect(self.toggle_fullscreen_mode)
        self.gamepad.connected_changed.connect(self._on_gamepad_connected)
        if os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen":
            self.gamepad.start()

    def _layout_chrome(self) -> None:
        if not hasattr(self, "stack"):
            return
        root = self.centralWidget()
        width = root.width() if root is not None and root.width() > 0 else self.width()
        height = root.height() if root is not None and root.height() > 0 else self.height()
        self.stack.setGeometry(0, 0, width, height)
        sidebar_x = self._sidebar_width - self._sidebar_expanded_width
        self.sidebar.setVisible((not self._fullscreen_mode) and self._sidebar_width > 0)
        self.sidebar.setGeometry(sidebar_x, 0, self._sidebar_expanded_width, height)
        self.topbar.setVisible(not self._fullscreen_mode)
        self.topbar.setGeometry(
            self._sidebar_width, 0, max(0, width - self._sidebar_width), self._topbar_height
        )
        self.sidebar.raise_()
        self.topbar.raise_()
        if hasattr(self, "_gamepad_bar") and self._gamepad_bar.isVisible():
            self._gamepad_bar.adjustSize()
            bar_w = min(width - 40, self._gamepad_bar.sizeHint().width())
            bar_h = self._gamepad_bar.sizeHint().height()
            self._gamepad_bar.setGeometry(
                max(20, (width - bar_w) // 2),
                max(10, height - bar_h - 14),
                bar_w,
                bar_h,
            )
            self._gamepad_bar.raise_()
        if hasattr(self, "toast") and self.toast.isVisible():
            self.toast.raise_()
        if hasattr(self, "update_banner") and self.update_banner.isVisible():
            self.update_banner.raise_()
        if hasattr(self, "_startup_overlay") and self._startup_overlay is not None and self._startup_overlay.isVisible():
            self._startup_overlay.setGeometry(0, 0, width, height)
            self._startup_overlay.raise_()

    def _apply_sidebar_width(self, value) -> None:
        self._sidebar_width = max(0, int(value))
        current = self.stack.currentWidget()
        if current is self.library:
            self.library.set_chrome_insets(self._sidebar_width, self._topbar_height)
        elif current is not None:
            current.setContentsMargins(self._sidebar_width, self._topbar_height, 0, 0)
        self._layout_chrome()

    def _on_sidebar_anim_finished(self) -> None:
        self.library.canvas.set_chrome_animating(False)
        for padded_page in (self.home, self.stats, self.health, self.settings_page):
            padded_page.setContentsMargins(self._sidebar_width, self._topbar_height, 0, 0)
        self.library.set_chrome_insets(self._sidebar_width, self._topbar_height)

    def _sync_sidebar_toggle(self) -> None:
        if self._sidebar_collapsed:
            self.sidebar_toggle.set_icon_name("chevron_right")
            self.sidebar_toggle.setToolTip("Mostrar barra lateral")
        else:
            self.sidebar_toggle.set_icon_name("chevron_left")
            self.sidebar_toggle.setToolTip("Ocultar barra lateral")

    def _toggle_sidebar(self) -> None:
        self._sidebar_collapsed = not self._sidebar_collapsed
        self._sync_sidebar_toggle()
        target = 0 if self._sidebar_collapsed else self._sidebar_expanded_width
        if is_reduced_motion() or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
            self._apply_sidebar_width(target)
            self._on_sidebar_anim_finished()
            return
        self._sidebar_anim.stop()
        self.library.canvas.prepare_chrome_transition(target)
        self._sidebar_anim.setStartValue(self._sidebar_width)
        self._sidebar_anim.setEndValue(target)
        self._sidebar_anim.start()

    def showEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().showEvent(event)
        self._layout_chrome()
        self._sync_nav_indicator(animate=False)
        self._sync_sys_indicator(animate=False)
        self._apply_titlebar()

    def _apply_titlebar(self) -> None:
        if os.name != "nt":
            return
        try:
            import ctypes

            value = ctypes.c_int(1 if is_dark(active()) else 0)
            handle = int(self.winId())
            for attribute in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    handle, attribute, ctypes.byref(value), ctypes.sizeof(value)
                )
                if result == 0:
                    break
        except Exception:
            pass

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            from .theme_extra import extra_qss

            style = active()
            accent = str(self.store.settings.get("accent") or "").strip() or style.accent
            sheet = qss(accent, style.key) + extra_qss(style)
            app.setStyleSheet(sheet)
        current_style = active()
        if hasattr(self, "_search_icon_action"):
            self._search_icon_action.setIcon(vector_icon("search", current_style.muted, 14))
        if hasattr(self, "_search_clear_action"):
            self._search_clear_action.setIcon(vector_icon("close", current_style.muted, 13))
        for button in self.findChildren(UmbralButton):
            button.refresh_icon()

    def _bootstrap(self) -> None:
        if self._closing:
            return
        stored = self.store.settings.get("emulators", [])
        self.emulators = [
            Emulator.from_dict(item) for item in stored if isinstance(item, dict)
        ]
        self._refresh_all()
        notice = getattr(self.store, "recovery_notice", "")
        if notice:
            QTimer.singleShot(2800, lambda text=notice: self.toast.show_message(text, 7000))
        self._detect_and_merge()
        self.store.settings["first_run"] = False
        self.store.save_settings()
        QTimer.singleShot(2800, self._fetch_missing_covers)
        QTimer.singleShot(2800, self._auto_check_updates)
        QTimer.singleShot(2800, self._restore_known_update)

    def _fetch_missing_covers(self) -> None:
        if self._closing:
            return
        if self.cover_worker is not None and self.cover_worker.isRunning():
            return
        pending = [game for game in self.store.games if cover_needs_refresh(game)]
        if not pending:
            return
        self._manual_covers_scan = False
        self.cover_worker = CoverWorker(pending, missing_only=True)
        self.cover_worker.finished_with.connect(self._on_covers_done)
        self.cover_worker.finished.connect(self._clear_cover_worker)
        self.cover_worker.start()

    def _refresh_covers(self) -> None:
        if self.cover_worker is not None and self.cover_worker.isRunning():
            self.toast.show_message("Ya se están buscando carátulas.")
            return
        if not self.store.games:
            self.toast.show_message("No hay juegos en la biblioteca.")
            return
        self._manual_covers_scan = True
        self.cover_worker = CoverWorker(list(self.store.games), missing_only=False)
        self.cover_worker.finished_with.connect(self._on_covers_done)
        self.cover_worker.finished.connect(self._clear_cover_worker)
        self.cover_worker.start()
        self.toast.show_message("Buscando carátulas para todos los juegos…")

    def _on_covers_done(self, found: int, errors: int) -> None:
        manual = self._manual_covers_scan
        self._manual_covers_scan = False
        if found:
            self._attach_covers()
            self.store.save_library()
            self._refresh_all()
            if manual:
                self.toast.show_message(f"Carátulas añadidas: {found}.")

    def _attach_covers(self) -> None:
        for game in self.store.games:
            path = game_cover(game)
            if path is not None:
                game.cover = str(path)

    def _clear_cover_worker(self) -> None:
        if self.cover_worker is not None:
            self.cover_worker.deleteLater()
            self.cover_worker = None

    def _notice_downloads(self) -> None:
        from ..downloads import pending_downloads

        mykey = getattr(self, "_notice_key", "")
        hidden_paths = {
            _path_key(str(item))
            for item in self.store.settings.get("hidden_paths", [])
        }
        try:
            pending = pending_downloads(
                self.store.settings.get("scan_folders", []), games=self.store.games
            )
        except Exception:  # noqa: BLE001 - un aviso no debe romper el arranque
            return
        fresh = [
            item
            for item in pending
            if not item.partial
            and _path_key(str(item.path)) not in hidden_paths
            and not any(
                _path_key(game.rom_path) == _path_key(str(item.path))
                for game in self.store.games
                if game.rom_path
            )
        ]
        if not fresh:
            return
        key = "|".join(sorted(_path_key(str(item.path)) for item in fresh))
        if key == mykey:
            return
        self._notice_key = key
        names = ", ".join(item.path.name for item in fresh[:2])
        extra = f" y {len(fresh) - 2} más" if len(fresh) > 2 else ""
        self.toast.show_message(
            f"Descarga detectada: {names}{extra}. Búscala en «Buscar juegos».", 6000
        )

    def _start_detect(
        self,
        *,
        announce: bool = False,
        prune: bool = False,
        clear_cache: bool = False,
        busy_message: str = "Ya hay una detección en marcha.",
        start_message: str = "Volviendo a detectar juegos…",
    ) -> None:
        if prune:
            self._prune_after_detect = True
        if self.detect_worker is not None and self.detect_worker.isRunning():
            if announce:
                self._detect_announce = True
                self.toast.show_message(start_message if prune else busy_message)
            return
        self._detect_announce = announce
        self.detect_worker = DetectWorker(
            self.store.settings.get("emulator_paths", {}),
            self.store.settings.get("scan_folders", []),
            custom_profiles(self.store.settings.get("custom_emulators", [])),
            clear_cache=clear_cache,
        )
        self.detect_worker.done.connect(self._on_detect_done)
        self.detect_worker.failed.connect(self._on_detect_failed)
        self.detect_worker.finished.connect(self._clear_detect_worker)
        self.detect_worker.start()
        if announce:
            self.toast.show_message(start_message)

    def _detect_and_merge(self, announce: bool = False) -> None:
        self._start_detect(announce=announce, prune=False, clear_cache=False)

    def _refresh_paths(self) -> None:
        if hasattr(self, "refresh_button"):
            self.refresh_button.set_loading(True, "Refrescando…")
        self._start_detect(
            announce=True,
            prune=True,
            clear_cache=True,
            start_message="Refrescando rutas de la biblioteca…",
        )

    def _on_detect_done(self, result) -> None:
        prune = self._prune_after_detect
        announce = self._detect_announce
        self._prune_after_detect = False
        self._detect_announce = False
        if hasattr(self, "refresh_button"):
            self.refresh_button.set_loading(False)

        self.emulators = result.emulators
        self.store.settings["emulators"] = [emulator.to_dict() for emulator in result.emulators]
        self.store.settings["detection_version"] = DETECTION_VERSION

        relocated = 0
        removed: list[Game] = []
        if prune:
            relocated = relocate_missing_paths(
                self.store.games,
                result.emulators,
                self.store.settings.get("scan_folders", []),
            )

        self.store.merge_detected(result.games)
        if prune:
            removed = self.store.prune_missing({game.id for game in result.games})

        self.store.save_library()
        self.store.save_settings()
        self._last_detection_log = list(getattr(result, "diagnostics", []))
        self._write_detection_log(self._last_detection_log)
        self._refresh_all()

        if prune:
            if removed and relocated:
                self.toast.show_message(
                    f"Rutas refrescadas: {relocated} actualizada(s) y {len(removed)} juego(s) quitado(s)."
                )
            elif len(removed) == 1:
                self.toast.show_message(f"Rutas refrescadas: se quitó «{removed[0].title}».")
            elif removed:
                self.toast.show_message(
                    f"Rutas refrescadas: {len(removed)} juegos no encontrados quitados."
                )
            elif relocated == 1:
                self.toast.show_message("Rutas refrescadas: 1 ruta actualizada.")
            elif relocated:
                self.toast.show_message(f"Rutas refrescadas: {relocated} rutas actualizadas.")
            else:
                self.toast.show_message("Rutas refrescadas: todos los juegos siguen en su sitio.")
        elif announce:
            self.toast.show_message(
                f"Detección terminada: {len(result.games)} juegos y {len(result.emulators)} perfiles."
            )
        self._notice_downloads()
        QTimer.singleShot(800, self._fetch_missing_covers)

    def _on_detect_failed(self, message: str) -> None:
        self._prune_after_detect = False
        self._detect_announce = False
        if hasattr(self, "refresh_button"):
            self.refresh_button.set_loading(False)
        self._show_error("No se pudo completar la detección", message)

    def _clear_detect_worker(self) -> None:
        if self.detect_worker is not None:
            self.detect_worker.deleteLater()
            self.detect_worker = None

    def _write_detection_log(self, lines: list[str]) -> None:
        try:
            path = data_dir() / "detection.log"
            stamp = datetime.now().isoformat(timespec="seconds")
            with path.open("w", encoding="utf-8") as handle:
                handle.write(f"Umbral {__version__} · detección {stamp}\n")
                for line in lines:
                    handle.write(f"{line}\n")
        except OSError:
            pass

    def _export_diagnostics(self) -> None:
        from PySide6.QtCore import QStandardPaths

        folder = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation) or str(data_dir())
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar diagnóstico",
            str(Path(folder) / "umbral-diagnostico.txt"),
            "Texto (*.txt)",
        )
        if not target:
            return
        lines = [
            f"Umbral {__version__}",
            f"Fecha: {datetime.now().isoformat(timespec='seconds')}",
            f"Sistema: {platform.platform()}",
            f"Python: {sys.version.split()[0]}",
            f"Datos: {data_dir()}",
            "",
            "Biblioteca:",
            f"  Juegos: {len(self.store.games)}",
            f"  Con incidencias: {sum(1 for game in self.store.games if validate(game))}",
            "",
            "Emuladores:",
        ]
        for emulator in self.emulators:
            state = "OK" if emulator.found else "NO"
            lines.append(f"  [{state}] {emulator.name}: {emulator.executable or emulator.note}")
        lines.append("")
        lines.append("Última detección:")
        for line in getattr(self, "_last_detection_log", []):
            lines.append(f"  {line}")
        try:
            Path(target).write_text("\n".join(lines), encoding="utf-8")
        except OSError as exc:
            self.toast.show_message(f"No se pudo guardar el diagnóstico: {exc}")
            return
        self.toast.show_message("Diagnóstico exportado.")

    def _refresh_all(self) -> None:
        self.home.refresh()
        self.library.refresh()
        self.stats.refresh()
        self.health.set_emulators(self.emulators)
        self.health.refresh()
        self.settings_page.set_emulators(self.emulators)
        self.settings_page.set_profiles(all_profiles(self.store.settings))
        self.settings_page.refresh()
        self._rebuild_systems()

    def _move_indicator(
        self, indicator: QFrame, anim: QPropertyAnimation, target: Optional[QPushButton], animate: bool = True
    ) -> None:
        if target is None or not target.isVisibleTo(target.parentWidget()):
            indicator.hide()
            return
        dest = target.geometry()
        if dest.width() <= 0 or dest.height() <= 0:
            QTimer.singleShot(
                0, lambda ind=indicator, an=anim, btn=target: self._move_indicator(ind, an, btn, animate=False)
            )
            return
        indicator.lower()
        indicator.show()
        anim.stop()
        if not animate or is_reduced_motion() or indicator.geometry().height() <= 0:
            indicator.setGeometry(dest)
            return
        anim.setStartValue(indicator.geometry())
        anim.setEndValue(dest)
        anim.start()

    def _sync_nav_indicator(self, animate: bool = True) -> None:
        target = self.nav_buttons.get(self._current_page_key)
        self._move_indicator(self._nav_indicator, self._nav_anim, target, animate=animate)

    def _sync_sys_indicator(self, animate: bool = True) -> None:
        key = self._current_page_key
        page = self.pages.get(key, self.library)
        active_sys = ""
        if key == "favorites":
            active_sys = self.library.current_filter()
        elif page in (self.home, self.library):
            active_sys = page.current_filter()
        target = self._system_buttons.get(active_sys)
        self._move_indicator(self._sys_indicator, self._sys_anim, target, animate=animate)

    def _rebuild_systems(self) -> None:
        key = self._current_page_key
        page = self.pages.get(key, self.library)
        games = self.store.games
        favorites_only = key == "favorites" or (page is self.library and self.library._favorites_only)
        if favorites_only:
            games = [game for game in games if game.favorite]
        counts: dict[str, list] = {}
        for game in games:
            entry = counts.setdefault(game.system_key, [game.system, 0])
            entry[1] += 1
        systems = sorted(
            ((sys_key, value[0], value[1]) for sys_key, value in counts.items()),
            key=lambda item: (-item[2], item[1]),
        )
        active = ""
        if key == "favorites":
            active = self.library.current_filter()
        elif page in (self.home, self.library):
            active = page.current_filter()

        signature = tuple(systems)
        if signature != self._systems_signature:
            self._systems_signature = signature
            self._system_buttons = {}
            clear_layout(self.systems_box)
            if systems:
                total = QPushButton("Todos")
                total.setObjectName("system")
                total.setCheckable(True)
                total.setFocusPolicy(Qt.NoFocus)
                total.setCursor(Qt.PointingHandCursor)
                total.clicked.connect(lambda _checked=False: self._filter_system(""))
                self.systems_box.addWidget(total)
                self._system_buttons[""] = total
                for system_key, label, count in systems:
                    button = QPushButton(f"{label}   {count}")
                    button.setObjectName("system")
                    button.setCheckable(True)
                    button.setFocusPolicy(Qt.NoFocus)
                    button.setCursor(Qt.PointingHandCursor)
                    button.clicked.connect(
                        lambda _checked=False, value=system_key: self._filter_system(value)
                    )
                    self.systems_box.addWidget(button)
                    self._system_buttons[system_key] = button
            else:
                empty = QLabel("Sin sistemas todavía")
                empty.setObjectName("tiny")
                self.systems_box.addWidget(empty)
            animate_sys = False
        else:
            animate_sys = True

        for sys_key, button in self._system_buttons.items():
            button.setChecked(sys_key == active)

        filterable = key in ("home", "library", "favorites")
        self.systems_section.setVisible(filterable)
        if filterable:
            self._sync_sys_indicator(animate=animate_sys)
        else:
            self._sys_indicator.hide()
        self._rebuild_collections(filterable and key in ("library", "favorites"))

    def _rebuild_collections(self, visible: bool = True) -> None:
        if not hasattr(self, "collections_section"):
            return
        self.collections_section.setVisible(visible)
        if not visible:
            return
        clear_layout(self.collections_box)
        self._collection_buttons = {}
        cols = self.store.collections()
        active_col = self.library.current_collection_filter()
        if not cols:
            empty = QLabel("Sin colecciones")
            empty.setObjectName("tiny")
            self.collections_box.addWidget(empty)
            return
        all_btn = QPushButton("Todas")
        all_btn.setObjectName("system")
        all_btn.setCheckable(True)
        all_btn.setChecked(not active_col)
        all_btn.setFocusPolicy(Qt.NoFocus)
        all_btn.setCursor(Qt.PointingHandCursor)
        all_btn.clicked.connect(lambda _c=False: self._filter_collection(""))
        self.collections_box.addWidget(all_btn)
        self._collection_buttons[""] = all_btn
        for name, count in cols:
            btn = QPushButton(f"{name}   {count}")
            btn.setObjectName("system")
            btn.setCheckable(True)
            btn.setChecked(active_col == name)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, v=name: self._filter_collection(v))
            self.collections_box.addWidget(btn)
            self._collection_buttons[name] = btn

    def _filter_collection(self, name: str) -> None:
        if self._current_page_key not in ("library", "favorites"):
            self._navigate("library")
        self.library.set_collection_filter(name)
        for col_name, btn in self._collection_buttons.items():
            btn.setChecked(col_name == name)

    def _create_collection_prompt(self, game: Optional[Game] = None) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Nueva colección", "Nombre de la colección:")
        clean = name.strip() if ok else ""
        if not clean:
            return
        self.store.add_collection(clean)
        if game is not None and clean not in game.collections:
            game.collections.append(clean)
            self.store.save_library()
        self._refresh_all()
        self.toast.show_message(f"Colección «{clean}» creada.")

    def _filter_system(self, key: str) -> None:
        page = self.pages.get(self._current_page_key, self.library)
        if self._current_page_key == "favorites":
            self.library.set_filter(key)
        elif page is self.home or page is self.library:
            page.set_filter(key)
        self._rebuild_systems()
        if self.stack.currentWidget() is self.library:
            self.library.focus_canvas()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if (
            self.stack.currentWidget() is self.library
            and self.library._view_mode == "shelf"
            and not isinstance(self.focusWidget(), QLineEdit)
            and event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down)
        ):
            self.library.canvas.keyPressEvent(event)
            return
        super().keyPressEvent(event)

    def _navigate(self, key: str, system_filter: Optional[str] = None) -> None:
        self._current_page_key = "favorites" if key == "favorites" else key
        if key == "favorites":
            self.library.set_mode(True)
            if system_filter:
                self.library.set_filter(system_filter)
            index = self.stack.indexOf(self.library)
        elif key == "library":
            self.library.set_mode(False)
            if system_filter:
                self.library.set_filter(system_filter)
            index = self.stack.indexOf(self.library)
        else:
            page = self.pages.get(key, self.home)
            index = self.stack.indexOf(page)

        if self.stack.currentIndex() != index:
            self.stack.setCurrentIndex(index)
            target_page = self.stack.currentWidget()
            if (
                target_page is not None
                and not is_reduced_motion()
                and os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen"
            ):
                from PySide6.QtWidgets import QGraphicsOpacityEffect

                effect = QGraphicsOpacityEffect(target_page)
                effect.setOpacity(0.15)
                target_page.setGraphicsEffect(effect)
                anim = QPropertyAnimation(effect, b"opacity", target_page)
                anim.setDuration(165)
                anim.setStartValue(0.15)
                anim.setEndValue(1.0)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.finished.connect(lambda w=target_page: w.setGraphicsEffect(None))
                self._page_anim = anim
                anim.start()
        if key in ("library", "favorites"):
            self.library.focus_canvas()
        for name, button in self.nav_buttons.items():
            button.setChecked(name == self._current_page_key)
        self._sync_nav_indicator(animate=True)
        self._rebuild_systems()

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _search(self, text: str) -> None:
        if hasattr(self, "_search_clear_action"):
            self._search_clear_action.setVisible(bool(text))
        if not text.strip():
            self.library.set_query("")
            self._rebuild_systems()
            return
        was_favorites = self._current_page_key == "favorites"
        self.library.set_mode(False)
        self.library.set_query(text)
        self.library.set_filter("")
        if was_favorites:
            self._current_page_key = "library"
            for name, button in self.nav_buttons.items():
                button.setChecked(name == "library")
        if self.stack.currentWidget() is not self.library:
            self._navigate("library")
        self._rebuild_systems()

    def _emulator_candidates(self, game: Game) -> list[tuple[Emulator, EmulatorProfile]]:
        if game.source in {"steam", "epic", "gog", "standalone"}:
            return []
        if game.emulator_locked:
            return []
        if game.source == "manual" and game.executable and Path(game.executable).is_file():
            return []
        if not game.rom_path and game.system_key != "ports":
            return []
        profiles = {profile.key: profile for profile in all_profiles(self.store.settings)}
        result: list[tuple[Emulator, EmulatorProfile]] = []
        for emulator in self.emulators:
            if not emulator.found:
                continue
            profile = profiles.get(emulator.key)
            if profile is None or profile.system_key != game.system_key:
                continue
            result.append((emulator, profile))
        if game.system_key == "ports":
            executable_name = Path(game.executable).name.lower() if game.executable else ""
            by_executable = [
                pair for pair in result if executable_name and executable_name in pair[1].wanted_names
            ]
            if by_executable:
                return by_executable[:1]
            if game.emulator:
                by_name = [
                    pair for pair in result if pair[0].name.lower() == game.emulator.lower()
                ]
                if by_name:
                    return by_name[:1]
            return []
        return result

    def _play(self, game: Game) -> None:
        if any(watcher.game_id == game.id and watcher.isRunning() for watcher in self.watchers):
            self.toast.show_message(f"{game.title} ya está en ejecución.")
            return
        candidates = self._emulator_candidates(game)
        if len(candidates) > 1:
            dialog = EmulatorChoiceDialog(
                game, [emulator for emulator, _profile in candidates], self
            )
            if dialog.exec() != QDialog.Accepted or dialog.chosen is None:
                return
            chosen = dialog.chosen
            profile = next(
                profile for emulator, profile in candidates if emulator.key == chosen.key
            )
            game.emulator = chosen.name
            game.executable = chosen.executable
            game.arguments = list(profile.arguments)
            game.working_dir = str(working_dir_for(profile, chosen.executable))
            game.emulator_locked = True
            self.store.save_library()
        issues = validate(game)
        if issues:
            self._show_error("No se puede lanzar", "\n".join(issues), game)
            return
        try:
            process, log_path = launch_game(game)
        except LaunchError as error:
            self._show_error(error.summary, error.details, game)
            return

        game.last_played = now_iso()
        self.store.save_library()
        self._refresh_all()
        self.toast.show_message(f"Lanzando {game.title}…")

        if game.source == "steam":
            app_id = steam_app_id(game)
            if not app_id:
                return
            watcher = SteamWatcher(app_id, log_path, game_id=game.id)
        else:
            watcher = ProcessWatcher(process, log_path, game_id=game.id)
        watcher.finished_ok.connect(
            lambda code, seconds, path, game_id=game.id: self._on_process_finished(
                game_id, int(code), int(seconds), Path(path)
            )
        )
        watcher.finished.connect(lambda worker=watcher: self._cleanup_watcher(worker))
        watcher.start()
        self.watchers.append(watcher)

    def _cleanup_watcher(self, watcher: ProcessWatcher) -> None:
        if watcher in self.watchers:
            self.watchers.remove(watcher)
        if not self.watchers and getattr(self, "_update_pending_banner", False):
            self._update_pending_banner = False
            info = self.update_info
            if info is not None:
                QTimer.singleShot(1500, lambda: self._show_update_banner(info))

    def _announce_update(self, info) -> None:
        if self.watchers:
            self._update_pending_banner = True
            self.toast.show_message("Actualización disponible. Se avisará al cerrar el juego.", 5000)
            return
        self._show_update_banner(info)

    def _show_update_banner(self, info) -> None:
        if self.update_banner.isVisible() and self.update_banner.current_version() == info.version:
            self.update_banner.raise_()
            return
        self.update_banner.show_update(info.version, getattr(info, "notes", ""))
        self.update_banner.raise_()

    def _restore_known_update(self) -> None:
        if self._closing or self.update_info is not None:
            return
        stored = self.store.settings.get("update_known")
        if not isinstance(stored, dict):
            return
        try:
            info = UpdateInfo(**stored)
        except TypeError:
            self.store.settings.pop("update_known", None)
            self.store.save_settings()
            return
        if not is_newer(info.version, __version__):
            self.store.settings.pop("update_known", None)
            self.store.settings.pop("update_dismissed_version", None)
            self.store.save_settings()
            return
        self.update_info = info
        self.settings_page.set_update_available(info)
        dismissed = str(self.store.settings.get("update_dismissed_version", ""))
        if dismissed != info.version:
            self._announce_update(info)

    def _on_process_finished(self, game_id: str, code: int, seconds: int, log_path: Path) -> None:
        game = self.store.get(game_id)
        if game is None:
            return
        if seconds >= 5:
            game.touch_play(seconds)
            self.store.save_library()
            self._refresh_all()
            if code != 0 and seconds < 30:
                self._show_error(
                    "El juego se cerró con un error",
                    f"Código de salida: {code}\nRegistro: {log_path}\n"
                    "La sesión se ha guardado igualmente.",
                    game,
                )
            else:
                suffix = "" if code == 0 else f" (código {code})"
                self.toast.show_message(
                    f"Sesión guardada: {game.title} · {game.playtime_text}{suffix}"
                )
            return
        if code != 0:
            self._show_error(
                "El juego se cerró con un error",
                f"Código de salida: {code}\nRegistro: {log_path}",
                game,
            )
            return
        if seconds < 3:
            self.toast.show_message("El juego se cerró casi al instante. Revisa la receta en su ficha.")

    def _details(self, game: Game) -> None:
        dialog = GameDetailDialog(game, self)
        dialog.play_requested.connect(self._play)
        dialog.edit_requested.connect(self._edit_game)
        dialog.delete_requested.connect(self._remove_game)
        dialog.changed.connect(self._save_and_refresh)
        dialog.exec()

    def _remove_game(self, game: Game) -> None:
        self.store.hide(game.id)
        self.store.save_library()
        self._refresh_all()
        self.toast.show_message(f"«{game.title}» quitado de Umbral.")

    def _save_and_refresh(self) -> None:
        self.store.save_library()
        self._refresh_all()

    def _add_game(self) -> None:
        dialog = AddGameDialog(self, store=self.store, emulators=self.emulators)
        if dialog.exec() == QDialog.Accepted:
            game = dialog.game()
            if game:
                self.store.upsert(game)
                self.store.save_library()
                self._refresh_all()
                self.toast.show_message(f"{game.title} añadido a la biblioteca.")
                QTimer.singleShot(300, self._fetch_missing_covers)

    def _edit_game(self, game: Game) -> None:
        previous_cover = game.cover
        dialog = AddGameDialog(self, game, store=self.store, emulators=self.emulators)
        if dialog.exec() == QDialog.Accepted:
            edited = dialog.game()
            if edited:
                if previous_cover and not edited.cover:
                    clear_cover_cache(edited)
                self.store.upsert(edited)
                self.store.save_library()
                self._refresh_all()
                self.toast.show_message("Ficha actualizada.")
                if not edited.cover:
                    QTimer.singleShot(300, self._fetch_missing_covers)

    def _show_game_menu(self, game: Game, global_pos) -> None:
        menu = QMenu(self)
        play_action = menu.addAction("Jugar ahora")
        details_action = menu.addAction("Ver ficha")
        menu.addSeparator()
        fav_action = menu.addAction("Quitar de favoritos" if game.favorite else "Añadir a favoritos")
        done_action = menu.addAction(
            "Desmarcar terminado" if game.progress == "finished" else "Marcar terminado"
        )
        edit_action = menu.addAction("Editar ficha")
        col_menu = menu.addMenu("Colecciones")
        col_actions: dict[QAction, str] = {}
        for col_name, _count in self.store.collections():
            act = col_menu.addAction(col_name)
            act.setCheckable(True)
            act.setChecked(col_name in game.collections)
            col_actions[act] = col_name
        if col_actions:
            col_menu.addSeparator()
        new_col_action = col_menu.addAction("Nueva colección…")
        backdrop_action = menu.addAction("Buscar fondo en internet...")
        restore_bg_action = (
            menu.addAction("Restaurar fondo por defecto") if game.backdrop else None
        )
        manual_action = (
            menu.addAction("Abrir manual (PDF)")
            if game.manual_path and Path(game.manual_path).is_file()
            else None
        )
        folder_action = menu.addAction("Abrir carpeta")
        menu.addSeparator()
        remove_action = menu.addAction("Quitar de Umbral")

        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if chosen is play_action:
            self._play(game)
        elif chosen is details_action:
            self._details(game)
        elif chosen is fav_action:
            game.favorite = not game.favorite
            self._save_and_refresh()
        elif chosen is done_action:
            game.progress = "" if game.progress == "finished" else "finished"
            self._save_and_refresh()
        elif chosen is edit_action:
            self._edit_game(game)
        elif chosen in col_actions:
            col_name = col_actions[chosen]
            if col_name in game.collections:
                game.collections = [c for c in game.collections if c != col_name]
            else:
                game.collections.append(col_name)
            self._save_and_refresh()
        elif chosen is new_col_action:
            self._create_collection_prompt(game)
        elif chosen is backdrop_action:
            self._pick_game_backdrop(game)
        elif restore_bg_action is not None and chosen is restore_bg_action:
            game.backdrop = ""
            self.library.canvas._backdrop_cache.clear()
            self._save_and_refresh()
            self.toast.show_message("Fondo restaurado.")
        elif manual_action is not None and chosen is manual_action:
            self._open_path(Path(game.manual_path))
        elif chosen is folder_action:
            self._open_game_folder(game)
        elif chosen is remove_action:
            answer = QMessageBox.question(
                self,
                "Quitar de Umbral",
                f"¿Quitar «{game.title}» de la biblioteca?\n\n"
                "No se borra ningún archivo del juego.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                self._remove_game(game)

    def _pick_game_backdrop(self, game: Game) -> None:
        from .backdrop_dialog import BackdropPickerDialog

        dialog = BackdropPickerDialog(game, self)
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.restore_default:
            game.backdrop = ""
            self.library.canvas._backdrop_cache.clear()
            self._save_and_refresh()
            self.toast.show_message("Fondo restaurado.")
        elif dialog.selected_path:
            game.backdrop = dialog.selected_path
            self.library.canvas._backdrop_cache.clear()
            self._save_and_refresh()
            self.toast.show_message("Fondo actualizado.")

    def _open_game_folder(self, game: Game) -> None:
        candidates: list[str] = []
        if game.rom_path:
            rom = Path(game.rom_path)
            candidates.append(str(rom if rom.is_dir() else rom.parent))
        if game.working_dir:
            candidates.append(game.working_dir)
        if game.executable:
            candidates.append(str(Path(game.executable).parent))
        for folder in candidates:
            if folder and Path(folder).is_dir():
                self._open_path(Path(folder))
                return
        self.toast.show_message("No se encontró la carpeta del juego.")

    def _open_path(self, path: Path) -> None:
        try:
            if hasattr(os, "startfile"):
                os.startfile(path)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except OSError:
            pass

    def _rescan(self) -> None:
        self._detect_and_merge(announce=True)

    def _relink_game(self, game: Game) -> None:
        parts = missing_parts(game)
        if not parts:
            self.toast.show_message("Ese juego ya tiene todas sus rutas en su sitio.")
            return
        part = parts[0]
        label = "la ROM o carpeta del juego" if part == "rom" else "el ejecutable del emulador o del port"
        if part == "rom":
            allowed = CONSOLE_EXTENSIONS.get(game.system_key, ())
            if game.system_key in {"pc", "ports"} and not Path(game.rom_path).suffix:
                path = QFileDialog.getExistingDirectory(
                    self, f"Selecciona la carpeta para {game.title}"
                )
            elif allowed:
                patterns = " ".join(f"*{extension}" for extension in allowed)
                path, _ = QFileDialog.getOpenFileName(
                    self,
                    f"Selecciona {label} de {game.title}",
                    "",
                    f"Archivos compatibles ({patterns});;Todos los archivos (*)",
                )
            else:
                path, _ = QFileDialog.getOpenFileName(
                    self, f"Selecciona {label} de {game.title}", "", "Todos los archivos (*)"
                )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, f"Selecciona {label} de {game.title}", "", executable_file_filter()
            )
        if not path:
            return
        if not relink(game, part, path):
            self.toast.show_message("Esa ruta no es válida para reasignar el juego.")
            return
        self.store.save_library()
        self._refresh_all()
        self.toast.show_message(f"Ruta actualizada para {game.title}.")
        remaining = missing_parts(game)
        if remaining:
            self.toast.show_message(
                f"Queda otra ruta por asignar en {game.title}. Pulsa Reasignar de nuevo.",
                6000,
            )

    def _scan_pc_games(self) -> None:
        if self.scan_worker is not None and self.scan_worker.isRunning():
            self.toast.show_message("Ya hay una búsqueda en marcha.")
            return
        self.scan_worker = ScanWorker(
            self.store.settings.get("scan_folders", []),
            include_steam=bool(self.store.settings.get("steam_scrape", True)),
            include_downloads=True,
            emulator_paths=self.store.settings.get("emulator_paths", {}),
            extra_profiles=custom_profiles(self.store.settings.get("custom_emulators", [])),
        )
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.results.connect(self._on_scan_results)
        self.scan_worker.failed.connect(self._on_scan_failed)
        self.scan_worker.finished.connect(self._clear_scan_worker)
        if hasattr(self, "scan_button"):
            self.scan_button.set_loading(True, "Buscando…")
        self.scan_worker.start()
        self.toast.show_message("Buscando juegos en tus carpetas…")

    def _on_scan_progress(self, text: str) -> None:
        self.toast.show_message(text, 2600)

    def _on_scan_failed(self, message: str) -> None:
        if hasattr(self, "scan_button"):
            self.scan_button.set_loading(False)
        self._show_error("La búsqueda no terminó", message)

    def _clear_scan_worker(self) -> None:
        if hasattr(self, "scan_button"):
            self.scan_button.set_loading(False)
        if self.scan_worker is not None:
            self.scan_worker.deleteLater()
            self.scan_worker = None

    def _on_scan_results(
        self,
        candidates: list[StandaloneCandidate],
        pending: list[Download],
        emulated: list[Game],
        emulators: list[object],
    ) -> None:
        if emulators:
            self.emulators = emulators
            self.store.settings["emulators"] = [
                emulator.to_dict() for emulator in emulators
            ]
            self.store.save_settings()
            self._refresh_all()

        known = {_path_key(game.executable) for game in self.store.games if game.executable}
        hidden = {str(item) for item in self.store.settings.get("hidden_games", [])}
        hidden_paths = {
            _path_key(str(item))
            for item in self.store.settings.get("hidden_paths", [])
        }
        fresh = [
            candidate
            for candidate in candidates
            if _path_key(str(candidate.executable)) not in known
            and _path_key(str(candidate.executable)) not in hidden_paths
        ]
        existing_ids = {game.id for game in self.store.games}
        emulated_known = {
            _path_key(game.rom_path) for game in self.store.games if game.rom_path
        }
        new_games = [
            game
            for game in emulated
            if game.id not in existing_ids
            and game.id not in hidden
            and (not game.rom_path or _path_key(game.rom_path) not in emulated_known)
            and (not game.rom_path or _path_key(game.rom_path) not in hidden_paths)
            and (
                game.rom_path
                or game.system_key not in {"pc", "ports"}
                or _path_key(game.executable) not in hidden_paths
            )
        ]
        store_fresh = [game for game in new_games if game.source in {"steam", "epic", "gog"}]
        emulated_fresh = [game for game in new_games if game.source not in {"steam", "epic", "gog"}]
        downloaded_known = {_path_key(game.rom_path) for game in self.store.games if game.rom_path}
        pending = [
            download
            for download in pending
            if _path_key(str(download.path)) not in downloaded_known
            and _path_key(str(download.path)) not in hidden_paths
        ]
        if not fresh and not pending and not emulated_fresh and not store_fresh:
            self.toast.show_message("No hay juegos nuevos que añadir.")
            return

        dialog = GameScanDialog(
            fresh, pending, self, emulated=emulated_fresh, stores=store_fresh
        )
        dialog.add_requested.connect(self._add_scan_selection)
        dialog.recheck_requested.connect(self._recheck_scan)
        dialog.exec()

    def _recheck_scan(self) -> None:
        self._clear_scan_worker()
        self._scan_pc_games()

    def _add_scan_selection(self, selection: list[object]) -> None:
        added = 0
        downloads: list[Download] = []
        existing_ids = {game.id for game in self.store.games}
        existing_roms = {
            _path_key(game.rom_path) for game in self.store.games if game.rom_path
        }
        existing_executables = {
            _path_key(game.executable)
            for game in self.store.games
            if game.executable
            and game.system_key in {"pc", "ports", "steam", "epic", "gog"}
        }
        for item in selection:
            game: Optional[Game] = None
            if isinstance(item, StandaloneCandidate):
                game = item.to_game()
            elif isinstance(item, Game):
                game = item
            elif isinstance(item, Download):
                game = self._game_from_download(item)
                if game is not None:
                    downloads.append(item)
            if game is None:
                continue
            if game.id in existing_ids:
                continue
            if game.rom_path and _path_key(game.rom_path) in existing_roms:
                continue
            if (
                not game.rom_path
                and game.executable
                and _path_key(game.executable) in existing_executables
            ):
                continue
            self.store.upsert(game)
            existing_ids.add(game.id)
            if game.rom_path:
                existing_roms.add(_path_key(game.rom_path))
            elif game.executable:
                existing_executables.add(_path_key(game.executable))
            added += 1
        mark_seen(downloads)
        self.store.save_library()
        self._refresh_all()
        if added:
            self.toast.show_message(f"{added} juego(s) añadidos a la biblioteca.")
            QTimer.singleShot(400, self._fetch_missing_covers)
        else:
            self.toast.show_message("No se añadió nada: ya estaban en la biblioteca.")

    def _game_from_download(self, download: Download) -> Optional[Game]:
        profile = emulator_for(download.path)
        if profile is None:
            return None
        emulator = next(
            (item for item in self.emulators if item.key == profile.key and item.found), None
        )
        if emulator is None:
            self.toast.show_message(
                f"Falta el emulador para {profile.system}. Configúralo en Ajustes."
            )
            return None
        from ..detect import clean_title

        title = clean_title(download.path.name)
        return Game(
            id=slugify(f"{profile.system_key}-{title}-{emulator.name}"),
            title=title,
            system=profile.system,
            system_key=profile.system_key,
            subtitle=f"{profile.system} · {emulator.name}",
            description=profile.description,
            executable=emulator.executable,
            arguments=list(profile.arguments),
            working_dir=str(Path(emulator.executable).parent),
            rom_path=str(download.path),
            emulator=emulator.name,
            accent=profile.accent,
            source="auto",
        )

    def _manage_emulators(self) -> None:
        dialog = EmulatorSetupDialog(self.store, self.emulators, self)
        if dialog.exec() == QDialog.Accepted:
            self._detect_and_merge(announce=True)

    def _set_accent(self, color: str) -> None:
        self.store.settings["accent"] = color
        self.store.save_settings()
        self._apply_theme()
        self._refresh_all()
        self.toast.show_message("Color de acento actualizado.")

    def _set_style(self, key: str) -> None:
        set_active(key)
        self.store.settings["style"] = key
        accent = active().accent
        self.store.settings["accent"] = accent
        self.store.save_settings()
        apply_style(key)
        self.backdrop.apply_style(key)
        self._apply_theme()
        self._apply_titlebar()
        self._refresh_all()
        self.toast.show_message(f"Estilo {active().name} aplicado.")

    def _set_halo(self, enabled: bool) -> None:
        self.library.canvas.set_halo_enabled(enabled)

    def _set_reduced_motion(self, enabled: bool) -> None:
        set_reduced_motion(enabled)
        self.toast.show_message(
            "Animaciones reducidas activadas." if enabled else "Animaciones completas activadas."
        )

    def _add_scan_folder(self) -> None:
        self.settings_page._add_folder()

    def _unhide_game(self, game_id: str) -> None:
        if self.store.unhide_game(game_id):
            self._refresh_all()
            self._detect_and_merge(announce=True)

    def _unhide_path(self, path_value: str) -> None:
        if self.store.unhide_path(path_value):
            self._refresh_all()
            self._detect_and_merge(announce=True)

    def _open_data(self) -> None:
        self._open_path(data_dir())

    def _export_library(self) -> None:
        from PySide6.QtCore import QStandardPaths

        folder = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation) or str(data_dir())
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar biblioteca",
            str(Path(folder) / "umbral-biblioteca.json"),
            "Biblioteca de Umbral (*.json)",
        )
        if not target:
            return
        try:
            self.store.export_library(Path(target))
        except OSError as exc:
            self.toast.show_message(f"No se pudo exportar la biblioteca: {exc}")
            return
        self.toast.show_message(f"Biblioteca exportada ({len(self.store.games)} juegos).")

    def _import_library(self) -> None:
        from PySide6.QtCore import QStandardPaths

        folder = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation) or str(data_dir())
        source, _ = QFileDialog.getOpenFileName(
            self,
            "Importar biblioteca",
            folder,
            "Biblioteca de Umbral (*.json)",
        )
        if not source:
            return
        try:
            added, updated = self.store.import_library(Path(source))
        except (OSError, ValueError) as exc:
            self.toast.show_message(f"No se pudo importar la biblioteca: {exc}")
            return
        self._refresh_all()
        self.toast.show_message(
            f"Importación completada: {added} añadidos, {updated} actualizados."
        )
        QTimer.singleShot(400, self._fetch_missing_covers)

    def _auto_check_updates(self) -> None:
        if self._closing or self._updating:
            return
        self._check_updates(manual=False)

    def _check_updates(self, manual: bool = False) -> None:
        if self._updating:
            return
        if self.update_worker is not None and self.update_worker.isRunning():
            if manual:
                self.toast.show_message("Ya se está comprobando la actualización.")
            return
        self.update_button.setEnabled(False)
        self.update_button.setText("Comprobando…")
        self.settings_page.set_update_checking(True)
        worker = CheckWorker(__version__, self)
        worker.found.connect(
            lambda info, manual=manual: self._on_update_checked(info, manual)
        )
        worker.failed.connect(
            lambda message, manual=manual: self._on_update_failed(message, manual)
        )
        worker.finished.connect(self._clear_update_worker)
        self.update_worker = worker
        worker.start()

    def _clear_update_worker(self) -> None:
        if self.update_worker is not None:
            self.update_worker.deleteLater()
            self.update_worker = None

    def _on_update_checked(self, info, manual: bool) -> None:
        self.update_button.setEnabled(True)
        self.update_button.setText("Buscar actualizaciones")
        self.store.settings["update_last_check"] = _now_iso()
        if manual:
            self.store.settings.pop("update_dismissed_version", None)
        if info is not None:
            self.update_info = info
            self.store.settings["update_known"] = asdict(info)
            self.store.save_settings()
            self.settings_page.set_update_available(info)
            dismissed = str(self.store.settings.get("update_dismissed_version", ""))
            if manual or dismissed != info.version:
                self._announce_update(info)
            return
        self.update_info = None
        self.store.settings.pop("update_known", None)
        self.store.settings.pop("update_dismissed_version", None)
        self.store.save_settings()
        self.settings_page.available_update = None
        if manual:
            message = f"Umbral {__version__} está al día."
            self.settings_page.set_update_result(message)
            self.toast.show_message(message)
        else:
            self.settings_page.set_update_result("")

    def _on_update_failed(self, message: str, manual: bool) -> None:
        self.update_button.setEnabled(True)
        self.update_button.setText("Buscar actualizaciones")
        if manual:
            self.settings_page.set_update_result(message)
            self.toast.show_message(message, 6000)
        else:
            self.settings_page.set_update_result("")

    def _postpone_update(self) -> None:
        if self.update_info is not None:
            self.store.settings["update_dismissed_version"] = self.update_info.version
            self.store.save_settings()
        self.update_banner.hide()
        self.settings_page.dismiss_update()

    def _install_update(self) -> None:
        if self._updating:
            self.toast.show_message("La actualización ya se está aplicando.")
            return
        info = self.update_info
        if info is None:
            self.update_banner.hide()
            self.toast.show_message("No hay una actualización lista. Compruebo de nuevo…", 5000)
            self._check_updates(manual=True)
            return
        if not getattr(sys, "frozen", False):
            binary_label = "Umbral.exe" if os.name == "nt" else "el ejecutable compilado de Umbral"
            message = (
                f"La actualización automática solo funciona desde {binary_label} "
                "(ahora mismo estás ejecutando main.py con Python)."
            )
            if self.update_banner.isVisible():
                self.update_banner.show_error(message)
            self.settings_page.set_update_error(message)
            self.toast.show_message(message, 6000)
            return
        try:
            self._download_update_inline(info)
        except Exception as exc:  # noqa: BLE001 - un fallo aquí no debe dejar el botón muerto
            message = f"No se pudo iniciar la descarga: {exc}"
            self.update_banner.show_error(message)
            self.settings_page.set_update_error(message)
            self.toast.show_message(message, 6000)

    def _download_update_inline(self, info) -> None:
        if self.download_worker is not None and self.download_worker.isRunning():
            if not self.update_banner.isVisible():
                self.update_banner.show_update(info.version, getattr(info, "notes", ""))
            self.update_banner.show_progress(0, 0)
            self.toast.show_message("La descarga ya está en marcha.")
            return
        if not self.update_banner.isVisible():
            self.update_banner.show_update(info.version, getattr(info, "notes", ""))
        self.update_banner.show_progress(0, 0)
        self.settings_page.set_update_downloading(0, 0)
        self.toast.show_message(f"Actualización solicitada · descargando Umbral {info.version}…", 4000)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        download = DownloadWorker(info, self)
        download.progress.connect(self.update_banner.show_progress)
        download.progress.connect(self.settings_page.set_update_downloading)
        download.done.connect(self._on_update_downloaded)
        download.failed.connect(self._on_update_download_failed)
        download.finished.connect(self._clear_download_worker)
        self.download_worker = download
        download.start()

    def _clear_download_worker(self) -> None:
        if self.download_worker is not None:
            self.download_worker.deleteLater()
            self.download_worker = None

    def _on_update_download_failed(self, message: str) -> None:
        if not self.update_banner.isVisible():
            if self.update_info is not None:
                self.update_banner.show_update(
                    self.update_info.version, getattr(self.update_info, "notes", "")
                )
            else:
                self.update_banner.show_update("")
        self.update_banner.show_error(message)
        self.settings_page.set_update_error(message)
        self.toast.show_message(message, 6000)

    def _on_update_downloaded(self, path: str) -> None:
        if self._updating:
            return
        self._updating = True
        self.update_banner.show_installing()
        self.settings_page.set_update_installing()
        self.toast.show_message("Descarga completa · instalando y reiniciando…", 4000)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        QTimer.singleShot(60, lambda target_path=path: self._finalize_update_install(target_path))

    def _finalize_update_install(self, path: str) -> None:
        try:
            backup_data(__version__)
        except OSError:
            pass
        try:
            apply_update(Path(path))
        except UpdateError as exc:
            self._updating = False
            message = str(exc)
            self.update_banner.show_error(message)
            self.settings_page.set_update_error(message)
            self.toast.show_message(message, 6000)
            return
        self.store.save_library()
        self.store.save_settings()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _show_error(self, title: str, details: str, game: Optional[Game] = None) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Umbral")
        box.setText(title)
        first_line = details.splitlines()[0] if details else "Revisa la configuración del juego."
        box.setInformativeText(first_line)
        full = details
        if game:
            full = diagnostic_text(game) + "\n\n" + details
        box.setDetailedText(full)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_chrome()
        self._sync_nav_indicator(animate=False)
        self._sync_sys_indicator(animate=False)
        if hasattr(self, "toast"):
            self.toast.reposition()
        if hasattr(self, "update_banner"):
            self.update_banner.reposition()

    def has_active_workers(self) -> bool:
        return any(
            worker is not None and worker.isRunning()
            for worker in (
                self.detect_worker,
                self.scan_worker,
                self.cover_worker,
                self.update_worker,
                self.download_worker,
            )
        )

    def _exit_fullscreen_if_active(self) -> None:
        if self._fullscreen_mode:
            self.toggle_fullscreen_mode()

    def toggle_fullscreen_mode(self) -> None:
        self._fullscreen_mode = not self._fullscreen_mode
        if self._fullscreen_mode:
            self._pre_fullscreen_collapsed = self._sidebar_collapsed
            self._sidebar_collapsed = True
            self._sidebar_width = 0
            self._topbar_height = 0
            if self._current_page_key not in ("library", "favorites"):
                self._navigate("library")
            self.library.set_chrome_insets(0, 0)
            self._gamepad_bar.show()
            if os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen":
                self.showFullScreen()
            self.library.focus_canvas()
        else:
            self._gamepad_bar.hide()
            self._topbar_height = 84
            self._sidebar_collapsed = self._pre_fullscreen_collapsed
            self._sidebar_width = 0 if self._sidebar_collapsed else self._sidebar_expanded_width
            self._sync_sidebar_toggle()
            for padded_page in (self.home, self.stats, self.health, self.settings_page):
                padded_page.setContentsMargins(self._sidebar_width, self._topbar_height, 0, 0)
            self.library.set_chrome_insets(self._sidebar_width, self._topbar_height)
            if os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen":
                self.showNormal()
        self._layout_chrome()

    def _on_gamepad_connected(self, connected: bool) -> None:
        if connected:
            self.toast.show_message("Mando conectado: navega con cruceta/stick y pulsa A para jugar.", 3600)

    def _gamepad_left(self) -> None:
        if self._current_page_key in ("library", "favorites"):
            self.library.canvas.step(-1)

    def _gamepad_right(self) -> None:
        if self._current_page_key in ("library", "favorites"):
            self.library.canvas.step(1)

    def _gamepad_up(self) -> None:
        if self._current_page_key in ("library", "favorites"):
            game = self.library.canvas.current_game()
            if game is not None:
                self._details(game)

    def _gamepad_down(self) -> None:
        if self._current_page_key in ("library", "favorites"):
            self.library.canvas.toggle_flip()

    def _gamepad_confirm(self) -> None:
        if self._current_page_key in ("library", "favorites"):
            game = self.library.canvas.current_game()
            if game is not None:
                self._play(game)

    def _gamepad_back(self) -> None:
        if self._fullscreen_mode:
            self.toggle_fullscreen_mode()
        elif self._current_page_key != "library":
            self._navigate("library")

    def _gamepad_flip(self) -> None:
        if self._current_page_key in ("library", "favorites"):
            self.library.canvas.toggle_flip()

    def _gamepad_favorite(self) -> None:
        if self._current_page_key in ("library", "favorites"):
            game = self.library.canvas.current_game()
            if game is not None:
                game.favorite = not game.favorite
                self._save_and_refresh()
                self.toast.show_message(
                    f"«{game.title}» añadido a favoritos." if game.favorite else f"«{game.title}» quitado de favoritos."
                )

    def _gamepad_cycle_system(self, delta: int) -> None:
        keys = [""] + [key for key, _lbl, _cnt in self.store.systems()]
        if not keys:
            return
        current = self.library.current_filter()
        idx = keys.index(current) if current in keys else 0
        next_key = keys[(idx + delta) % len(keys)]
        self._filter_system(next_key)

    def closeEvent(self, event) -> None:
        self._closing = True
        if hasattr(self, "gamepad"):
            self.gamepad.stop()
        if hasattr(self, "backdrop"):
            self.backdrop.stop()
        for watcher in list(self.watchers):
            if watcher.isRunning():
                elapsed = watcher.elapsed_seconds()
                if elapsed >= 5:
                    target = self.store.get(watcher.game_id)
                    if target is not None:
                        target.touch_play(elapsed)
                try:
                    watcher.finished_ok.disconnect()
                    watcher.finished.disconnect()
                except (RuntimeError, TypeError):
                    pass
                if hasattr(watcher, "stop"):
                    watcher.stop()
                    watcher.wait(1500)
                watcher.setParent(None)
        self.store.save_library()
        self.store.save_settings()
        worker_wait = 150 if self._updating else 800
        update_wait = 150 if self._updating else 800
        download_wait = 200 if self._updating else 800
        cover_wait = 150 if self._updating else 800
        for worker in (self.detect_worker, self.scan_worker):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(worker_wait)
        if self.update_worker is not None and self.update_worker.isRunning():
            self.update_worker.requestInterruption()
            self.update_worker.wait(update_wait)
        if self.download_worker is not None and self.download_worker.isRunning():
            self.download_worker.cancel()
            self.download_worker.wait(download_wait)
        if self.cover_worker is not None and self.cover_worker.isRunning():
            self.cover_worker.cancel()
            self.cover_worker.wait(cover_wait)
        super().closeEvent(event)
