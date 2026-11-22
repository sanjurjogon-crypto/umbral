import sys

sys.path.insert(0, r"C:\Users\sanju\Desktop\umbral")

from PySide6.QtWidgets import QApplication

from umbral.ui.main_window import MainWindow

app = QApplication(sys.argv)
window = MainWindow()
window.showMaximized()
app.processEvents()
window.toast.hide()
window._navigate("home")
app.processEvents()
app.processEvents()
window.toast.hide()
print("home:", window.grab().save(r"C:\Users\sanju\Desktop\umbral\oro_home.png"))
window._navigate("library")
app.processEvents()
app.processEvents()
window.toast.hide()
print("library:", window.grab().save(r"C:\Users\sanju\Desktop\umbral\oro_library.png"))
