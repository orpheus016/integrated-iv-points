# main.py
import sys
from PySide6.QtWidgets import QApplication
from main_window import MainWindow

def main():
    
    app = QApplication(sys.argv)

    from style import BACKGROUND_COLOR
    app.setStyleSheet(
        f"QMessageBox {{ background-color: {BACKGROUND_COLOR}; }}\n"
        "QLabel { color: black; background-color: transparent; }\n"
        "QPushButton { color: black; }"
    )

    window = MainWindow()
    window.showFullScreen()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

