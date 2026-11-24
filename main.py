from __future__ import annotations

import os
import sys
import threading
import time

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from umbral.paths import assets_dir
from umbral.ui.main_window import MainWindow

INSTANCE_KEY = os.environ.get("UMBRAL_INSTANCE_KEY") or "Umbral-single-instance"


def _show_window(window: MainWindow) -> None:
    window.showMaximized()
    window.raise_()
    window.activateWindow()


def _notify_existing() -> bool:
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_KEY)
    if not socket.waitForConnected(400):
        return False
    socket.write(b"show")
    socket.flush()
    socket.waitForBytesWritten(400)
    socket.disconnectFromServer()
    return True


def _listen(holder: dict[str, MainWindow | None]) -> QLocalServer | None:
    server = QLocalServer()
    if not server.listen(INSTANCE_KEY):
        return None

    def accept() -> None:
        connection = server.nextPendingConnection()
        if connection is not None:
            connection.deleteLater()
        window = holder.get("window")
        if window is not None:
            _show_window(window)

    server.newConnection.connect(accept)
    return server


def _load_fonts() -> None:
    folder = assets_dir() / "fonts"
    if not folder.is_dir():
        return
    for path in sorted(folder.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(path))


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Umbral")
    app.setApplicationDisplayName("Umbral")
    app.setOrganizationName("Umbral")
    app.setStyle("Fusion")
    _load_fonts()
    app.setFont(QFont("EB Garamond", 11))
    icon_path = assets_dir() / "umbral.ico"
    if not icon_path.exists():
        icon_path = assets_dir() / "umbral.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    holder: dict[str, MainWindow | None] = {"window": None}
    relaunching = "--relaunch" in sys.argv[1:]
    if relaunching:
        deadline = time.monotonic() + 2.0
        server = _listen(holder)
        while server is None and time.monotonic() < deadline:
            time.sleep(0.1)
            QLocalServer.removeServer(INSTANCE_KEY)
            server = _listen(holder)
        if server is None:
            QLocalServer.removeServer(INSTANCE_KEY)
            server = _listen(holder)
    else:
        if _notify_existing():
            return 0
        server = _listen(holder)
        if server is None:
            if _notify_existing():
                return 0
            QLocalServer.removeServer(INSTANCE_KEY)
            server = _listen(holder)
    if server is not None:
        app.aboutToQuit.connect(server.close)
    window = MainWindow()
    holder["window"] = window
    window.showMaximized()
    code = app.exec()
    if server is not None:
        server.close()
        app.processEvents()
    has_bg_threads = any(
        thread is not threading.main_thread() and thread.is_alive()
        for thread in threading.enumerate()
    )
    if window.has_active_workers() or has_bg_threads or window._updating:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
