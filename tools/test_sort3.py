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

page.sort_combo.setCurrentIndex(page.sort_combo.findData("title"))
app.processEvents()
print("title btn:", page.order_button.text().encode("ascii", "replace").decode())
page.sort_combo.setCurrentIndex(page.sort_combo.findData("hours"))
app.processEvents()
print("hours btn:", page.order_button.text().encode("ascii", "replace").decode())
print("hours asc flag:", page._sort_asc)
page._toggle_order()
app.processEvents()
print("toggled btn:", page.order_button.text().encode("ascii", "replace").decode())
window.toast.hide()
app.processEvents()
print("capture:", window.grab().save(r"C:\Users\sanju\Desktop\umbral\sort_test.png"))
