from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from umbral.paths import assets_dir
from umbral.ui.main_window import MainWindow

INSTANCE_KEY = "Umbral-single-instance"


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
    if _notify_existing():
        return 0
    holder: dict[str, MainWindow | None] = {"window": None}
    server = _listen(holder)
    if server is None:
        if _notify_existing():
            return 0
        QLocalServer.removeServer(INSTANCE_KEY)
        server = _listen(holder)
    window = MainWindow()
    holder["window"] = window
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
