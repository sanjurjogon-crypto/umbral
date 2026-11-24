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

    banner.show_progress(5 * 1024 * 1024, 10 * 1024 * 1024)
    assert "50 %" in banner.detail.text()
    assert "5,0 de 10,0 MB" in banner.detail.text()
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
