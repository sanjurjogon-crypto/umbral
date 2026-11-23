from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import main as entry


class FakeWindow:
    def __init__(self) -> None:
        self.shown = 0

    def showMaximized(self) -> None:
        self.shown += 1

    def raise_(self) -> None:
        pass

    def activateWindow(self) -> None:
        pass


def test_second_instance_notifies_first(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(entry, "INSTANCE_KEY", "Umbral-test-single-instance")
    holder = {"window": FakeWindow()}
    server = entry._listen(holder)
    assert server is not None
    try:
        assert entry._notify_existing() is True
        app.processEvents()
        assert holder["window"].shown >= 1
    finally:
        server.close()
        app.processEvents()
