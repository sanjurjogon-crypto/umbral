import sys

sys.path.insert(0, r"C:\Users\sanju\Desktop\umbral")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from umbral.store import Store
from umbral.ui.main_window import MainWindow

store = Store()
stored = store.settings.get("custom_emulators", [])
store.settings["custom_emulators"] = [
    item for item in stored if isinstance(item, dict) and item.get("key") != "custom-prueba"
]
store.save_settings()
print("custom_emulators:", store.settings["custom_emulators"])

app = QApplication(sys.argv)
window = MainWindow()
window.showMaximized()
QTest.qWait(300)
window.toast.hide()
window._navigate("library")
QTest.qWait(350)
page = window.library

def titles():
    return [item.game.title for item in page.canvas.items[:3]]

print("initial:", page.canvas.index, titles())
page.sort_combo.setCurrentIndex(page.sort_combo.findData("title"))
QTest.qWait(120)
page._toggle_order()
QTest.qWait(120)
print("desc:", page.canvas.index, titles())
page.sort_combo.setCurrentIndex(page.sort_combo.findData("hours"))
QTest.qWait(120)
print("hours:", page.canvas.index, titles())
print("current:", page.canvas.current_game().title if page.canvas.current_game() else None)
print("sort settings:", window.store.settings.get("sort_key"), window.store.settings.get("sort_asc"))
