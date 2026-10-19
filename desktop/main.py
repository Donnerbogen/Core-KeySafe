import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox
from core_keysafe.app import KeySafeWindow
from core_keysafe.paths import ensure_layout, create_desktop_shortcut

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CORE KeySafe")
    paths = ensure_layout()
    create_desktop_shortcut()
    window = KeySafeWindow(paths)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
