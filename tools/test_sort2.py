import sys

sys.path.insert(0, r"C:\Users\sanju\Desktop\umbral")

from PySide6.QtWidgets import QApplication

from umbral.ui.main_window import MainWindow

app = QApplication(sys.argv)
window = MainWindow()
app.processEvents()
page = window.library

print("combo", page.sort_combo.count())
print("default", page._sort_key, page._sort_asc)
print("btn", page.order_button.text().encode("ascii", "replace").decode())
print("asc", [g.title for g in page._visible_games()[:4]])
page.sort_combo.setCurrentIndex(page.sort_combo.findData("hours"))
app.processEvents()
print("hours desc", [(g.title, g.playtime_seconds) for g in page._visible_games()[:4]])
print("btn", page.order_button.text().encode("ascii", "replace").decode())
page._toggle_order()
app.processEvents()
print("hours asc", [(g.title, g.playtime_seconds) for g in page._visible_games()[:4]])
page.sort_combo.setCurrentIndex(page.sort_combo.findData("played"))
app.processEvents()
print("played desc", [(g.title, g.last_played[:10]) for g in page._visible_games()[:4]])
print("settings", window.store.settings.get("sort_key"), window.store.settings.get("sort_asc"))
