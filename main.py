"""StudioNermi Cloud Lab desktop application."""

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("StudioNermi Cloud Lab")
        self.resize(520, 360)
        self.setMinimumSize(360, 280)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(14)
        title = QLabel("StudioNermi Cloud Lab")
        title.setObjectName("title")
        layout.addWidget(title)
        self.file_label = QLabel("No file selected")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)
        layout.addStretch()

        self.open_button = QPushButton("Open File")
        self.settings_button = QPushButton("Settings")
        self.exit_button = QPushButton("Exit")
        for button in (self.open_button, self.settings_button, self.exit_button):
            layout.addWidget(button)
        self.open_button.clicked.connect(self.open_file)
        self.settings_button.clicked.connect(self.show_settings)
        self.exit_button.clicked.connect(self.close)
        self.setCentralWidget(content)
        self.setStyleSheet("""
            QWidget { background-color: #181b22; color: #edf0f7;
                      font-family: sans-serif; font-size: 14px; }
            QLabel#title { font-size: 23px; font-weight: bold; }
            QPushButton { background-color: #303849; border: 1px solid #536078;
                          border-radius: 6px; padding: 10px; }
            QPushButton:hover { background-color: #414e67; }
            QPushButton:pressed { background-color: #242c3b; }
            QPushButton:focus { border: 2px solid #9abaff; }
        """)

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open File")
        if filename:
            self.file_label.setText(f"Selected file: {Path(filename).name}")
            self.file_label.setToolTip(filename)

    def show_settings(self):
        QMessageBox.information(
            self,
            "Settings",
            "StudioNermi Cloud Lab uses a dark theme.\n"
            "There are no configurable settings yet.",
        )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("StudioNermi Cloud Lab")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
