import sys

sys.path.insert(0, r"C:\Users\sanju\Desktop\umbral")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from umbral.consoles import CONSOLES, CONSOLE_EXTENSIONS
from umbral.models import Emulator, Game
from umbral.profiles import all_profiles, profile_from_dict
from umbral.ui.dialogs import CustomEmulatorDialog, EmulatorChoiceDialog
from umbral.ui.main_window import MainWindow

app = QApplication(sys.argv)
print("consolas:", len(CONSOLES))
print("gba ext:", CONSOLE_EXTENSIONS["gba"])

custom = profile_from_dict(
    {
        "key": "custom-prueba",
        "name": "Prueba",
        "system": "GBA",
        "system_key": "gba",
        "executable": r"C:\Windows\System32\notepad.exe",
        "arguments": "{rom}",
        "rom_extensions": [".gba"],
    }
)
print("profile:", custom.key, custom.system_key, custom.exe_names, custom.arguments)

window = MainWindow()
window.showMaximized()
QTest.qWait(300)

store = window.store
store.settings["custom_emulators"] = [
    {
        "key": "custom-prueba",
        "name": "Prueba",
        "system": "GBA",
        "system_key": "gba",
        "executable": r"C:\Windows\System32\notepad.exe",
        "arguments": "{rom}",
        "rom_extensions": [".gba"],
    }
]
profiles = all_profiles(store.settings)
print("all profiles:", len(profiles), "last:", profiles[-1].key)

window.emulators = [
    Emulator(key="custom-prueba", name="Prueba", executable=r"C:\Windows\System32\notepad.exe", found=True),
    Emulator(key="mgba", name="mGBA", executable=r"C:\Windows\System32\notepad.exe", found=True),
]
game = Game(id="gba-demo", title="Demo GBA", system="GBA", system_key="gba", rom_path=r"C:\tmp\demo.gba")
print("candidates:", [emulator.name for emulator, _profile in window._emulator_candidates(game)])

window._refresh_all()
QTest.qWait(200)
window._navigate("settings")
QTest.qWait(400)
window.toast.hide()
QTest.qWait(100)
print("capture:", window.grab().save(r"C:\Users\sanju\Desktop\umbral\ajustes_consolas.png"))

dialog = CustomEmulatorDialog(window)
print("dialog consoles:", dialog.console_combo.count(), "ext:", dialog.ext_edit.text())
dialog.console_combo.setCurrentIndex(dialog.console_combo.findData("snes"))
print("snes ext:", dialog.ext_edit.text())

choice = EmulatorChoiceDialog(game, window.emulators, window)
print("choice buttons:", len(choice.findChildren(type(choice))), "chosen:", choice.chosen)
