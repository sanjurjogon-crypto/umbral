import sys

sys.path.insert(0, r"C:\Users\sanju\Desktop\umbral")

from PySide6.QtWidgets import QApplication

from umbral.ui.main_window import MainWindow

app = QApplication(sys.argv)
window = MainWindow()
window.showMaximized()
app.processEvents()

for key in ("souls", "mario"):
    window._set_style(key)
    window._navigate("library")
    app.processEvents()
    app.processEvents()
    window.toast.hide()
    app.processEvents()
    ok = window.grab().save(rf"C:\Users\sanju\Desktop\umbral\pack_{key}.png")
    print(key, "saved:", ok)
