from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from umbral.ui.widgets import UpdateBanner
from umbral.updater import UpdateInfo


def test_banner_without_version_shows_preparing() -> None:
    app = QApplication.instance() or QApplication([])
    banner = UpdateBanner()
    banner.show_update("")
    assert "Preparando" in banner.detail.text()
    assert "Gonzalo es el puto amo" in banner.line1.text()
    banner.close()
    app.processEvents()


def test_banner_shows_custom_message_and_progress() -> None:
    app = QApplication.instance() or QApplication([])
    banner = UpdateBanner()
    banner.show_update("8.21.1")
    assert banner.title.text() == "¡Estás de suerte! Ya que:"
    assert "Gonzalo es el puto amo" in banner.line1.text()
    assert "8.21.1" in banner.detail.text()

    banner.show_progress(0, 0)
    assert "Iniciando" in banner.title.text()
    assert "Solicitud recibida" in banner.detail.text()
    assert banner.progress_bar.isVisibleTo(banner)
    assert banner.progress_bar.maximum() == 0

    banner.show_progress(5 * 1024 * 1024, 10 * 1024 * 1024)
    assert "50 %" in banner.detail.text()
    assert "5,0 de 10,0 MB" in banner.detail.text()
    assert banner.progress_bar.maximum() == 100
    assert banner.progress_bar.value() == 50

    banner.show_installing()
    assert "Instalando" in banner.title.text()
    assert banner.progress_bar.value() == 100
    banner.close()
    app.processEvents()


def test_postpone_persists_dismissed_version_across_restore(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    from umbral.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.store.settings["update_last_check"] = "2099-01-01T00:00:00+00:00"
    info = UpdateInfo(
        version="99.0.0",
        tag="v99.0.0",
        notes="Novedad",
        asset_url="https://github.com/sanjurjogon-crypto/umbral/releases/download/v99.0.0/Umbral.exe",
        asset_name="Umbral.exe",
        size=1024,
        digest="",
        sha_url="",
        page_url="https://github.com/sanjurjogon-crypto/umbral/releases/tag/v99.0.0",
        published_at="",
    )
    window._on_update_checked(info, manual=False)
    assert window.store.settings["update_known"]["version"] == "99.0.0"

    window._postpone_update()
    assert window.store.settings["update_dismissed_version"] == "99.0.0"
    assert not window.update_banner.isVisible()

    # Simula un reinicio restaurando desde settings.json: no debe volver a abrir el banner.
    window.update_info = None
    window.update_banner.hide()
    window._restore_known_update()
    assert window.update_info is not None
    assert not window.update_banner.isVisible()
    assert window.settings_page.available_update is not None

    window.close()
    window.deleteLater()
    app.processEvents()


def test_settings_page_shows_download_progress_and_error(monkeypatch, tmp_path) -> None:
    from PySide6.QtWidgets import QPushButton

    import umbral.store as store_mod
    from umbral.ui.pages import SettingsPage

    monkeypatch.setattr(store_mod, "library_file", lambda: tmp_path / "library.json")
    monkeypatch.setattr(store_mod, "settings_file", lambda: tmp_path / "settings.json")
    app = QApplication.instance() or QApplication([])
    store = store_mod.Store()
    page = SettingsPage(store)
    info = UpdateInfo(
        version="8.23.1",
        tag="v8.23.1",
        notes="Corrección de actualización",
        asset_url="https://github.com/sanjurjogon-crypto/umbral/releases/download/v8.23.1/Umbral.exe",
        asset_name="Umbral.exe",
        size=1024,
        digest="",
        sha_url="",
        page_url="https://github.com/sanjurjogon-crypto/umbral/releases/tag/v8.23.1",
        published_at="",
    )
    page.set_update_available(info)
    assert page._update_install_btn is not None
    assert page._update_install_btn.text() == "Actualizar ahora"

    page.set_update_downloading(0, 0)
    assert page._update_install_btn.text() == "Conectando…"
    assert not page._update_install_btn.isEnabled()
    assert "Solicitud recibida" in page._update_status_note.text()
    assert page._update_progress_bar is not None
    assert page._update_progress_bar.maximum() == 0

    page.set_update_downloading(5 * 1024 * 1024, 10 * 1024 * 1024)
    assert page._update_install_btn.text() == "Descargando 50 %…"
    assert not page._update_install_btn.isEnabled()
    assert "50 %" in page._update_status_note.text()
    assert page._update_progress_bar.maximum() == 100
    assert page._update_progress_bar.value() == 50

    page.refresh()
    assert page._update_install_btn is not None
    assert not page._update_install_btn.isEnabled()
    assert "50 %" in page._update_status_note.text()
    assert page._update_progress_bar is not None
    assert page._update_progress_bar.value() == 50

    page.set_update_installing()
    assert page._update_install_btn.text() == "Instalando…"
    assert page._update_progress_bar.value() == 100

    page.set_update_error("Fallo de red")
    assert page._update_install_btn.text() == "Reintentar"
    assert page._update_install_btn.isEnabled()
    assert page._update_status_note.text() == "Fallo de red"
    assert not page._update_progress_bar.isVisibleTo(page)

    page.deleteLater()
    app.processEvents()


def test_banner_is_static_across_state_transitions_and_translucent() -> None:
    from PySide6.QtWidgets import QWidget

    from umbral.ui.style import UMBRAL_STYLE
    from umbral.ui.theme_extra import extra_qss

    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1280, 800)
    banner = UpdateBanner(host)

    banner.show_update("8.26.3")
    pos_initial = banner.pos()
    size_initial = banner.size()

    banner.show_progress(0, 0)
    app.processEvents()
    assert banner.pos() == pos_initial
    assert banner.size() == size_initial

    banner.show_progress(5 * 1024 * 1024, 10 * 1024 * 1024)
    app.processEvents()
    assert banner.pos() == pos_initial
    assert banner.size() == size_initial

    banner.show_installing()
    app.processEvents()
    assert banner.pos() == pos_initial
    assert banner.size() == size_initial

    banner.show_error("Fallo de prueba")
    app.processEvents()
    assert banner.pos() == pos_initial
    assert banner.size() == size_initial

    sheet = extra_qss(UMBRAL_STYLE)
    banner_block = sheet.split("QFrame#updateBanner {", 1)[1].split("}", 1)[0]
    assert "rgba(" in banner_block
    assert "rgba(255, 255, 255, 0.14)" in banner_block

    host.close()
    host.deleteLater()
    app.processEvents()


def test_banner_is_larger_has_no_graphics_effect_and_button_click_hits_visually() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QWidget

    app = QApplication.instance() or QApplication([])
    host = QWidget()
    host.resize(1280, 800)
    host.show()
    banner = UpdateBanner(host)
    clicks: list[str] = []
    banner.install_clicked.connect(lambda: clicks.append("install"))
    banner.postpone_clicked.connect(lambda: clicks.append("later"))

    banner.show_update("8.27.1")
    app.processEvents()

    assert banner.graphicsEffect() is None
    assert banner.width() >= 680
    assert banner.height() >= 320

    pos_before = banner.pos()
    banner.reposition()
    app.processEvents()
    assert banner.pos() == pos_before

    # Verify clicking the exact center of the visible action button hits cleanly
    QTest.mouseClick(banner.action, Qt.LeftButton, pos=banner.action.rect().center())
    QTest.mouseClick(banner.later, Qt.LeftButton, pos=banner.later.rect().center())
    app.processEvents()
    assert clicks == ["install", "later"]

    host.close()
    host.deleteLater()
    app.processEvents()
