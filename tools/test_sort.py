import sys

sys.path.insert(0, r"C:\Users\sanju\Desktop\umbral")

from PySide6.QtWidgets import QApplication

from umbral.ui.main_window import MainWindow

app = QApplication(sys.argv)
window = MainWindow()
window.showMaximized()
app.processEvents()
window.toast.hide()
window._navigate("library")
app.processEvents()
page = window.library

print("combo count:", page.sort_combo.count())
print("default key:", page._sort_key, "asc:", page._sort_asc)
print("button:", page.order_button.text())


def titles():
    return [game.title for game in page._visible_games()[:5]]


print("title asc:", titles())
page.sort_combo.setCurrentIndex(page.sort_combo.findData("hours"))
app.processEvents()
print("hours desc:", titles())
print("button now:", page.order_button.text())
page._toggle_order()
app.processEvents()
print("hours asc:", titles())
print("button now:", page.order_button.text())
page.sort_combo.setCurrentIndex(page.sort_combo.findData("title"))
app.processEvents()
window.toast.hide()
app.processEvents()
print("capture:", window.grab().save(r"C:\Users\sanju\Desktop\umbral\sort_test.png"))
