"""assets\\icon.ico yaratadi (build.bat chaqiradi)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QGuiApplication

app = QGuiApplication(sys.argv)
from ekran_yozuvchi.ui.appicon import write_ico

os.makedirs("assets", exist_ok=True)
write_ico(os.path.join("assets", "icon.ico"))
print("assets/icon.ico yaratildi")
