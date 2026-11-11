"""StudioNermi Cloud Lab 2.0: local, read-only project browsing."""

import keyword
import re
import sys
from pathlib import Path

from PySide6.QtCore import QDir, Qt
from PySide6.QtGui import QColor, QFontDatabase, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFileSystemModel, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTreeView,
    QVBoxLayout, QWidget,
)

VERSION = "2.0"
MAX_PREVIEW_BYTES = 1024 * 1024
OFFLINE_MESSAGE = "AI assistant is not yet connected to a cloud service. No messages or project files are sent. No API key is required."


class PythonHighlighter(QSyntaxHighlighter):
    """Highlight Python tokens and carry triple-quoted strings between blocks."""

    def highlightBlock(self, text):
        self.setCurrentBlockState(0)

        def paint(start, length, color):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            self.setFormat(start, length, fmt)

        token = re.compile(r"#[^\n]*|'''|\"\"\"|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b")
        offset = 0
        previous = self.previousBlockState()
        if previous in (1, 2):
            delimiter = "'''" if previous == 1 else '"""'
            end = text.find(delimiter)
            if end == -1:
                paint(0, len(text), "#b6d98c")
                self.setCurrentBlockState(previous)
                return
            offset = end + 3
            paint(0, offset, "#b6d98c")
        while match := token.search(text, offset):
            value = match.group()
            start, offset = match.span()
            if value in ("'''", '"""'):
                end = text.find(value, offset)
                if end == -1:
                    paint(start, len(text) - start, "#b6d98c")
                    self.setCurrentBlockState(1 if value == "'''" else 2)
                    return
                offset = end + 3
                paint(start, offset - start, "#b6d98c")
            elif value.startswith('#'):
                paint(start, len(value), "#8b9aaf")
            elif value.startswith(("'", '"')):
                paint(start, len(value), "#b6d98c")
            elif value in keyword.kwlist or value in ("match", "case"):
                paint(start, len(value), "#c5a3ff")
            elif value[0].isdigit():
                paint(start, len(value), "#f0bb7c")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project_path = None
        self.setWindowTitle("StudioNermi Cloud Lab 2.0")
        self.resize(1400, 850)
        self.setMinimumSize(960, 640)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        header = QHBoxLayout()
        title = QLabel("StudioNermi Cloud Lab 2.0")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        self.project_button = QPushButton("Open Project")
        self.open_button = QPushButton("Open File")
        self.settings_button = QPushButton("Settings")
        self.exit_button = QPushButton("Exit")
        for button in (self.project_button, self.open_button, self.settings_button, self.exit_button):
            header.addWidget(button)
        layout.addLayout(header)
        self.project_label = QLabel("Open a local folder to get started")
        self.project_label.setWordWrap(True)
        layout.addWidget(self.project_label)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        def panel(title):
            widget = QWidget()
            box = QVBoxLayout(widget)
            box.setContentsMargins(10, 10, 10, 10)
            label = QLabel(title)
            label.setObjectName("heading")
            box.addWidget(label)
            splitter.addWidget(widget)
            return box

        explorer = panel("Project Explorer")
        self.model = QFileSystemModel(self)
        self.model.setReadOnly(True)
        self.model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot | QDir.Filter.Hidden)
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(180)
        for column in range(1, self.model.columnCount()):
            self.tree.hideColumn(column)
        self.tree.setVisible(False)
        self.explorer_hint = QLabel("No project open")
        explorer.addWidget(self.explorer_hint, 1, Qt.AlignmentFlag.AlignTop)
        explorer.addWidget(self.tree, 1)
        preview = panel("Code Preview · Read only")
        self.file_label = QLabel("No file selected")
        self.file_label.setWordWrap(True)
        preview.addWidget(self.file_label)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select a file to preview its contents.")
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(12)
        self.preview.setFont(font)
        self.highlighter = PythonHighlighter(self.preview.document())
        preview.addWidget(self.preview, 1)
        assistant = panel("AI Assistant")
        notice = QLabel(OFFLINE_MESSAGE)
        notice.setWordWrap(True)
        assistant.addWidget(notice)
        self.chat = QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("Cloud connection coming in a future release.")
        assistant.addWidget(self.chat, 1)
        self.assistant_input = QLineEdit()
        self.assistant_input.setPlaceholderText("Type a message…")
        self.assistant_input.setAccessibleName("Message to AI assistant")
        assistant.addWidget(self.assistant_input)
        self.send_button = QPushButton("Send")
        assistant.addWidget(self.send_button)
        splitter.setSizes([260, 650, 360])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(QLabel("Local workspace  •  Files are previewed only  •  AI offline"))
        self.setCentralWidget(content)
        self.project_button.clicked.connect(self.open_project)
        self.open_button.clicked.connect(self.open_file)
        self.settings_button.clicked.connect(self.show_settings)
        self.exit_button.clicked.connect(self.close)
        self.tree.selectionModel().currentChanged.connect(self.select_file)
        self.send_button.clicked.connect(self.send_message)
        self.assistant_input.returnPressed.connect(self.send_message)
        self.setStyleSheet("""
            QWidget { background: #151922; color: #e7edf6; font-size: 16px; }
            QLabel#title { font-size: 26px; font-weight: bold; }
            QLabel#heading { color: #a9bfff; font-size: 18px; font-weight: bold; }
            QPushButton { background: #2c3952; border: 1px solid #536789;
                border-radius: 7px; padding: 11px 16px; min-height: 22px; }
            QPushButton:hover { background: #3a4e70; }
            QPushButton:pressed { background: #202c40; }
            QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus, QTreeView:focus {
                border: 2px solid #a9bfff; }
            QPlainTextEdit, QTreeView, QLineEdit { background: #10141c;
                border: 1px solid #354159; border-radius: 6px; padding: 8px;
                selection-background-color: #3a527e; }
            QTreeView::item { min-height: 32px; }
            QSplitter::handle { background: #354159; width: 3px; }
        """)

    def open_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Project")
        if not folder:
            return
        path = Path(folder)
        if not path.is_dir():
            QMessageBox.warning(self, "Open Project", "This folder is no longer available.")
            return
        self.project_path = path
        self.tree.setRootIndex(self.model.setRootPath(str(path)))
        self.tree.clearSelection()
        self.tree.show()
        self.explorer_hint.hide()
        self.project_label.setText(str(path))
        self.preview.clear()
        self.file_label.setText("No file selected")
        self.file_label.setToolTip("")

    def select_file(self, index, previous=None):
        if index.isValid() and not self.model.isDir(index):
            self.preview_file(Path(self.model.filePath(index)))

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open File")
        if filename:
            self.preview_file(Path(filename))

    def preview_file(self, path):
        self.file_label.setText(f"Selected file: {path.name}")
        self.file_label.setToolTip(str(path))
        self.highlighter.setDocument(self.preview.document() if path.suffix.lower() in (".py", ".pyw") else None)
        try:
            if not path.is_file():
                raise ValueError("Select a regular file to preview.")
            # Bounded reads also handle files that grow after selection.
            with path.open("rb") as source:
                data = source.read(MAX_PREVIEW_BYTES + 1)
            if len(data) > MAX_PREVIEW_BYTES:
                raise ValueError("File is too large to preview (maximum 1 MiB).")
            if b"\0" in data:
                raise ValueError("Binary files cannot be previewed.")
            text = data.decode("utf-8-sig")
        except UnicodeError:
            text = "Preview unavailable: this file is not UTF-8 text."
        except (OSError, ValueError) as error:
            text = f"Preview unavailable: {error}"
        self.preview.setPlainText(text)

    def send_message(self):
        message = self.assistant_input.text().strip()
        if not message:
            return
        self.chat.appendPlainText(f"You: {message}\n\nAssistant: {OFFLINE_MESSAGE}\n")
        self.assistant_input.clear()

    def show_settings(self):
        QMessageBox.information(self, "Settings", "StudioNermi Cloud Lab 2.0\n\n"
            "Appearance: dark theme with large, readable controls.\n"
            "Project files: read-only preview; never executed automatically.\n\n"
            + OFFLINE_MESSAGE + "\n\nThere are no configurable settings yet.")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("StudioNermi Cloud Lab")
    app.setApplicationVersion(VERSION)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
