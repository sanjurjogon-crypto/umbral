import sys

sys.path.insert(0, r"C:\Users\sanju\Desktop\umbral")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from umbral.ui.main_window import MainWindow

app = QApplication(sys.argv)
window = MainWindow()
window.showMaximized()
QTest.qWait(300)
window.toast.hide()
window._navigate("library")
QTest.qWait(350)
page = window.library

print("initial:", page.canvas.index, [g.title for g in page.canvas.items[:3]])
page.sort_combo.setCurrentIndex(page.sort_combo.findData("title"))
QTest.qWait(120)
page._toggle_order()
QTest.qWait(120)
print("desc:", page.canvas.index, [g.title for g in page.canvas.items[:3]])
print("current:", page.canvas.current_game().title if page.canvas.current_game() else None)
page.sort_combo.setCurrentIndex(page.sort_combo.findData("year"))
QTest.qWait(120)
print("year:", page.canvas.index, [g.title for g in page.canvas.items[:3]])
window.toast.hide()
QTest.qWait(100)
print("capture:", window.grab().save(r"C:\Users\sanju\Desktop\umbral\fluido.png"))
print("sheet combo:", "QComboBox::down-arrow" in app.styleSheet())
