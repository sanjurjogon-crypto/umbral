from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from umbral.ui.widgets import UpdateBanner


def test_banner_without_version_shows_preparing() -> None:
    app = QApplication.instance() or QApplication([])
    banner = UpdateBanner()
    banner.show_update("")
    assert "Preparando" in banner.detail.text()
    banner.close()
    app.processEvents()
