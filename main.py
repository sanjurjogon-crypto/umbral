from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from umbral.paths import assets_dir
from umbral.ui.main_window import MainWindow


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
    window = MainWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
