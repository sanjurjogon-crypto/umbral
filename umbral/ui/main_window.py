from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..cover_worker import CoverWorker
from ..covers import cover_needs_refresh, game_cover
from .. import __version__
from ..detect import DETECTION_VERSION
from ..downloads import Download, emulator_for, mark_seen
from ..launcher import LaunchError, ProcessWatcher, diagnostic_text, launch_game, validate
from ..models import Emulator, Game, now_iso, slugify
from ..paths import assets_dir, data_dir
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
from .pages import HealthPage, HomePage, LibraryPage, SettingsPage, StatsPage, clear_layout
from .shelf import apply_style
from .style import active, is_dark, set_active
from .theme import qss
from .update_dialog import CheckWorker, DownloadWorker
from .widgets import Backdrop, Toast, UpdateBanner


def _path_key(value: str) -> str:
    try:
        return os.path.normcase(os.path.abspath(value))
    except OSError:
        return os.path.normcase(value)


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
        self._detect_announce = False
        style_key = str(self.store.settings.get("style", "souls"))
        set_active(style_key)
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
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(238)
        sidebar_shell = QVBoxLayout(sidebar)
        sidebar_shell.setContentsMargins(0, 0, 0, 0)
        sidebar_shell.setSpacing(0)
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setObjectName("sidebarScroll")
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setFrameShape(QFrame.NoFrame)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_scroll.viewport().setAutoFillBackground(False)
        side_content = QWidget()
        side_content.setObjectName("sidebarContent")
        side_content.setAutoFillBackground(False)
        side = QVBoxLayout(side_content)
        side.setContentsMargins(18, 22, 18, 18)
        side.setSpacing(6)
        sidebar_scroll.setWidget(side_content)
        sidebar_shell.addWidget(sidebar_scroll)

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
        self.systems_box = QVBoxLayout()
        self.systems_box.setSpacing(1)
        systems_layout.addLayout(self.systems_box)
        side.addWidget(self.systems_section)

        side.addStretch(1)
        divider = QFrame()
        divider.setObjectName("divider")
        side.addWidget(divider)
        settings_button = QPushButton("Ajustes")
        settings_button.setObjectName("nav")
        settings_button.setCheckable(True)
        settings_button.setCursor(Qt.PointingHandCursor)
        settings_button.clicked.connect(lambda: self._navigate("settings"))
        self.nav_buttons["settings"] = settings_button
        side.addWidget(settings_button)
        self.version_label = QLabel(f"v{__version__} · biblioteca local")
        self.version_label.setObjectName("tiny")
        side.addWidget(self.version_label)
        credit = QLabel("Un proyecto de Gonzalo Sanjurjo")
        credit.setObjectName("tiny")
        credit.setWordWrap(True)
        credit.setStyleSheet(f"color: {active().accent_2};")
        side.addWidget(credit)

        content = QWidget()
        content_body = QVBoxLayout(content)
        content_body.setContentsMargins(0, 0, 0, 0)
        content_body.setSpacing(0)

        topbar = QFrame()
        topbar.setFixedHeight(84)
        top = QHBoxLayout(topbar)
        top.setContentsMargins(32, 18, 32, 10)
        top.setSpacing(14)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar en tu biblioteca...")
        self.search.setFixedWidth(320)
        self.search.textChanged.connect(self._search)
        top.addWidget(self.search)
        top.addStretch(1)
        add_button = QPushButton("＋  Añadir juego")
        add_button.setObjectName("primary")
        add_button.setCursor(Qt.PointingHandCursor)
        add_button.clicked.connect(self._add_game)
        top.addWidget(add_button)
        scan_button = QPushButton("Buscar juegos")
        scan_button.setObjectName("ghost")
        scan_button.setCursor(Qt.PointingHandCursor)
        scan_button.clicked.connect(self._scan_pc_games)
        top.addWidget(scan_button)
        content_body.addWidget(topbar)

        self.stack = QStackedWidget()
        self.home = HomePage(self.store)
        self.library = LibraryPage(self.store)
        self.stats = StatsPage(self.store)
        self.health = HealthPage(self.store)
        self.settings_page = SettingsPage(self.store)

        for page in (self.home, self.library):
            page.play_requested.connect(self._play)
            page.details_requested.connect(self._details)
            page.add_requested.connect(self._add_game)
        self.health.rescan_requested.connect(self._rescan)
        self.settings_page.rescan_requested.connect(self._rescan)
        self.settings_page.scan_pc_requested.connect(self._scan_pc_games)
        self.settings_page.covers_requested.connect(self._refresh_covers)
        self.settings_page.manage_emulators.connect(self._manage_emulators)
        self.settings_page.accent_changed.connect(self._set_accent)
        self.settings_page.style_changed.connect(self._set_style)
        self.settings_page.open_data.connect(self._open_data)
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
        content_body.addWidget(self.stack, 1)

        outer.addWidget(sidebar)
        outer.addWidget(content, 1)
        self.setCentralWidget(root)

        self.toast = Toast(self)
        self.update_banner = UpdateBanner(self)
        self.update_banner.install_clicked.connect(self._install_update)
        self.update_banner.postpone_clicked.connect(self._postpone_update)

        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(self._focus_search)
        rescan_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        rescan_shortcut.activated.connect(self._rescan)

    def showEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().showEvent(event)
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
            sheet = qss(style.accent, style.key) + extra_qss(style)
            app.setStyleSheet(sheet)

    def _bootstrap(self) -> None:
        stored = self.store.settings.get("emulators", [])
        self.emulators = [
            Emulator.from_dict(item) for item in stored if isinstance(item, dict)
        ]
        self._refresh_all()
        if self.store.games:
            self.toast.show_message(f"Biblioteca lista: {len(self.store.games)} juegos.")
        else:
            self.toast.show_message("No hay juegos todavía. Usa Añadir juego o revisa Ajustes.")
        self._detect_and_merge()
        self.store.settings["first_run"] = False
        self.store.save_settings()
        QTimer.singleShot(1200, self._fetch_missing_covers)
        QTimer.singleShot(4500, self._auto_check_updates)
        QTimer.singleShot(2600, self._restore_known_update)

    def _fetch_missing_covers(self) -> None:
        if self.cover_worker is not None and self.cover_worker.isRunning():
            return
        pending = [game for game in self.store.games if cover_needs_refresh(game)]
        if not pending:
            return
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
        self.cover_worker = CoverWorker(list(self.store.games), missing_only=False)
        self.cover_worker.finished_with.connect(self._on_covers_done)
        self.cover_worker.finished.connect(self._clear_cover_worker)
        self.cover_worker.start()
        self.toast.show_message("Buscando carátulas para todos los juegos…")

    def _on_covers_done(self, found: int, errors: int) -> None:
        if found:
            self._attach_covers()
            self.store.save_library()
            self._refresh_all()
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

    def _detect_and_merge(self, announce: bool = False) -> None:
        if self.detect_worker is not None and self.detect_worker.isRunning():
            if announce:
                self.toast.show_message("Ya hay una detección en marcha.")
            return
        self._detect_announce = announce
        self.detect_worker = DetectWorker(
            self.store.settings.get("emulator_paths", {}),
            self.store.settings.get("scan_folders", []),
            custom_profiles(self.store.settings.get("custom_emulators", [])),
        )
        self.detect_worker.done.connect(self._on_detect_done)
        self.detect_worker.failed.connect(self._on_detect_failed)
        self.detect_worker.finished.connect(self._clear_detect_worker)
        self.detect_worker.start()
        if announce:
            self.toast.show_message("Volviendo a detectar juegos…")

    def _on_detect_done(self, result) -> None:
        self.emulators = result.emulators
        self.store.settings["emulators"] = [emulator.to_dict() for emulator in result.emulators]
        self.store.settings["detection_version"] = DETECTION_VERSION
        self.store.merge_detected(result.games)
        self.store.save_library()
        self.store.save_settings()
        self._refresh_all()
        if self._detect_announce:
            self.toast.show_message(
                f"Detección terminada: {len(result.games)} juegos y {len(result.emulators)} perfiles."
            )
            self._detect_announce = False
        self._notice_downloads()

    def _on_detect_failed(self, message: str) -> None:
        self._detect_announce = False
        self._show_error("No se pudo completar la detección", message)

    def _clear_detect_worker(self) -> None:
        if self.detect_worker is not None:
            self.detect_worker.deleteLater()
            self.detect_worker = None

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

    def _rebuild_systems(self) -> None:
        clear_layout(self.systems_box)
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
            ((key, value[0], value[1]) for key, value in counts.items()),
            key=lambda item: (-item[2], item[1]),
        )
        active = ""
        if key == "favorites":
            active = self.library.current_filter()
        elif page in (self.home, self.library):
            active = page.current_filter()
        if systems:
            total = QPushButton("Todos")
            total.setObjectName("system")
            total.setCheckable(True)
            total.setChecked(not active)
            total.setCursor(Qt.PointingHandCursor)
            total.clicked.connect(lambda _checked=False: self._filter_system(""))
            self.systems_box.addWidget(total)
            for system_key, label, count in systems:
                button = QPushButton(f"{label}   {count}")
                button.setObjectName("system")
                button.setCheckable(True)
                button.setChecked(active == system_key)
                button.setCursor(Qt.PointingHandCursor)
                button.clicked.connect(
                    lambda _checked=False, value=system_key: self._filter_system(value)
                )
                self.systems_box.addWidget(button)
        else:
            empty = QLabel("Sin sistemas todavía")
            empty.setObjectName("tiny")
            self.systems_box.addWidget(empty)

        filterable = key in ("home", "library", "favorites")
        self.systems_section.setVisible(filterable)

    def _filter_system(self, key: str) -> None:
        page = self.pages.get(self._current_page_key, self.library)
        if self._current_page_key == "favorites":
            self.library.set_filter(key)
        elif page is self.home or page is self.library:
            page.set_filter(key)
        self._rebuild_systems()

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

        self.stack.setCurrentIndex(index)
        page_widget = self.stack.currentWidget()
        if page_widget is not None:
            fade = getattr(self, "_page_fade", None)
            if fade is not None:
                fade.stop()
            effect = QGraphicsOpacityEffect(page_widget)
            page_widget.setGraphicsEffect(effect)
            animation = QPropertyAnimation(effect, b"opacity", page_widget)
            animation.setDuration(180)
            animation.setStartValue(0.35)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            animation.finished.connect(lambda: page_widget.setGraphicsEffect(None))
            self._page_fade = animation
            animation.start()
        if key in ("library", "favorites"):
            self.library.focus_canvas()
        for name, button in self.nav_buttons.items():
            button.setChecked(name == key)
        self._rebuild_systems()

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _search(self, text: str) -> None:
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
        if game.source in {"steam", "epic", "standalone"}:
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
            game.working_dir = str(Path(chosen.executable).parent)
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

        if game.source in {"steam", "epic"}:
            return

        watcher = ProcessWatcher(process, log_path)
        watcher.finished_ok.connect(
            lambda code, seconds, path, target=game: self._on_process_finished(target, int(code), int(seconds), Path(path))
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
        self.update_banner.show_update(info.version)
        self.update_banner.raise_()

    def _restore_known_update(self) -> None:
        if self.update_info is not None:
            return
        stored = self.store.settings.get("update_known")
        if not isinstance(stored, dict):
            return
        try:
            info = UpdateInfo(**stored)
        except TypeError:
            return
        if not is_newer(info.version, __version__):
            self.store.settings.pop("update_known", None)
            self.store.save_settings()
            return
        self.update_info = info
        self.settings_page.set_update_available(info)
        self._announce_update(info)

    def _on_process_finished(self, game: Game, code: int, seconds: int, log_path: Path) -> None:
        if code == 0 and seconds >= 5:
            game.touch_play(seconds)
            self.store.save_library()
            self._refresh_all()
            self.toast.show_message(f"Sesión guardada: {game.title} · {game.playtime_text}")
            return
        if code != 0 and seconds < 30:
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
        dialog = AddGameDialog(self, game, store=self.store, emulators=self.emulators)
        if dialog.exec() == QDialog.Accepted:
            edited = dialog.game()
            if edited:
                self.store.upsert(edited)
                self.store.save_library()
                self._refresh_all()
                self.toast.show_message("Ficha actualizada.")

    def _rescan(self) -> None:
        self._detect_and_merge(announce=True)

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
        self.scan_worker.start()
        self.toast.show_message("Buscando juegos en tus carpetas…")

    def _on_scan_progress(self, text: str) -> None:
        self.toast.show_message(text, 2600)

    def _on_scan_failed(self, message: str) -> None:
        self._show_error("La búsqueda no terminó", message)

    def _clear_scan_worker(self) -> None:
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
        fresh = [
            candidate for candidate in candidates
            if _path_key(str(candidate.executable)) not in known
        ]
        existing_ids = {game.id for game in self.store.games}
        emulated_known = {
            _path_key(game.rom_path) for game in self.store.games if game.rom_path
        }
        new_games = [
            game for game in emulated
            if game.id not in existing_ids
            and (not game.rom_path or _path_key(game.rom_path) not in emulated_known)
        ]
        store_fresh = [game for game in new_games if game.source in {"steam", "epic"}]
        emulated_fresh = [game for game in new_games if game.source not in {"steam", "epic"}]
        downloaded_known = {_path_key(game.rom_path) for game in self.store.games if game.rom_path}
        pending = [
            download for download in pending
            if _path_key(str(download.path)) not in downloaded_known
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
        for item in selection:
            if isinstance(item, StandaloneCandidate):
                game = item.to_game()
                if self.store.get(game.id) is None:
                    self.store.upsert(game)
                    added += 1
            elif isinstance(item, Game):
                if self.store.get(item.id) is None:
                    self.store.upsert(item)
                    added += 1
            elif isinstance(item, Download):
                game = self._game_from_download(item)
                if game is not None and self.store.get(game.id) is None:
                    self.store.upsert(game)
                    downloads.append(item)
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

    def _open_data(self) -> None:
        try:
            os.startfile(data_dir())
        except OSError:
            pass

    def _auto_check_updates(self) -> None:
        if self._updating:
            return
        last = str(self.store.settings.get("update_last_check", ""))
        try:
            moment = datetime.fromisoformat(last.replace("Z", "+00:00"))
        except ValueError:
            moment = None
        if moment is not None:
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            elapsed = datetime.now(timezone.utc) - moment
            if timedelta(0) <= elapsed < timedelta(hours=24):
                return
        self._check_updates(manual=False)

    def _check_updates(self, manual: bool = False) -> None:
        if self._updating:
            return
        if self.update_worker is not None and self.update_worker.isRunning():
            if manual:
                self.toast.show_message("Ya se está comprobando la actualización.")
            return
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
        self.store.settings["update_last_check"] = _now_iso()
        if info is not None:
            self.update_info = info
            self.store.settings["update_known"] = asdict(info)
            self.store.save_settings()
            self.settings_page.set_update_available(info)
            self._announce_update(info)
            return
        self.update_info = None
        self.store.settings.pop("update_known", None)
        self.store.save_settings()
        self.settings_page.available_update = None
        if manual:
            message = f"Umbral {__version__} está al día."
            self.settings_page.set_update_result(message)
            self.toast.show_message(message)
        else:
            self.settings_page.set_update_result("")

    def _on_update_failed(self, message: str, manual: bool) -> None:
        if manual:
            self.settings_page.set_update_result(message)
            self.toast.show_message(message, 6000)
        else:
            self.settings_page.set_update_result("")

    def _postpone_update(self) -> None:
        self.update_banner.hide()

    def _install_update(self) -> None:
        if self._updating:
            return
        info = self.update_info
        if info is None:
            self.toast.show_message("Comprueba primero si hay una versión nueva.")
            return
        self._download_update_inline(info)

    def _download_update_inline(self, info) -> None:
        if self.download_worker is not None and self.download_worker.isRunning():
            return
        if not self.update_banner.isVisible():
            self.update_banner.show_update(info.version)
        self.update_banner.show_progress(0, 0)
        download = DownloadWorker(info, self)
        download.progress.connect(self.update_banner.show_progress)
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
        self.update_banner.show_error(message)

    def _on_update_downloaded(self, path: str) -> None:
        try:
            backup_data(__version__)
        except OSError:
            pass
        try:
            apply_update(Path(path))
        except UpdateError as exc:
            self.update_banner.show_error(str(exc))
            return
        self._updating = True
        self.store.save_library()
        self.store.save_settings()
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
        if hasattr(self, "toast"):
            self.toast.reposition()
        if hasattr(self, "update_banner"):
            self.update_banner.reposition()

    def closeEvent(self, event) -> None:
        self.store.save_library()
        self.store.save_settings()
        for worker in (self.detect_worker, self.scan_worker):
            if worker is not None and worker.isRunning():
                worker.wait(2500)
        if self.update_worker is not None and self.update_worker.isRunning():
            self.update_worker.wait(9000)
        if self.download_worker is not None and self.download_worker.isRunning():
            self.download_worker.cancel()
            self.download_worker.wait(4000)
        super().closeEvent(event)
