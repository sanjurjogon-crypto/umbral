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


def test_flush_std_streams_handles_none_streams(monkeypatch) -> None:
    import sys

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    entry._flush_std_streams()

    flushed: list[str] = []

    class DummyStream:
        def __init__(self, label: str, fail: bool = False) -> None:
            self._label = label
            self._fail = fail

        def flush(self) -> None:
            if self._fail:
                raise OSError("broken pipe")
            flushed.append(self._label)

    monkeypatch.setattr(sys, "stdout", DummyStream("out"))
    monkeypatch.setattr(sys, "stderr", DummyStream("err", fail=True))
    entry._flush_std_streams()
    assert flushed == ["out"]


def test_main_exits_cleanly_when_std_streams_are_none(monkeypatch, tmp_path) -> None:
    import sys

    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(entry, "INSTANCE_KEY", "Umbral-test-none-streams")
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    class StubWindow:
        def __init__(self) -> None:
            self._updating = True

        def showMaximized(self) -> None:
            pass

        def has_active_workers(self) -> bool:
            return False

    exited: list[int] = []
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(entry, "QApplication", lambda _argv: app)
    monkeypatch.setattr(entry, "MainWindow", StubWindow)
    monkeypatch.setattr(app, "exec", lambda: 0)
    monkeypatch.setattr(entry.os, "_exit", lambda code: exited.append(code))

    rc = entry.main()
    assert rc == 0
    assert exited == [0]
