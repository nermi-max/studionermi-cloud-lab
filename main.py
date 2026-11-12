"""StudioNermi Cloud Lab 3.1.1 — Microphone Test Edition: local, read-only project browsing."""

import keyword
import re
import sys
from pathlib import Path

from PySide6.QtCore import QDir, Qt
from PySide6.QtGui import QIcon, QColor, QFontDatabase, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFileSystemModel, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QTreeView,
    QVBoxLayout, QWidget,
)

from assistant import AssistantWorker, Credentials
from voice import MicrophoneTestWorker, VoiceWorker

VERSION = "3.1.1"
MAX_PREVIEW_BYTES = 1024 * 1024
CLOUD_MESSAGE = "OpenAI API · Chat text and dictation audio are sent only when requested. Project files are not uploaded. API billing is separate from ChatGPT Plus."


class SettingsDialog(QDialog):
    def __init__(self, credentials, model, parent=None, transcription_model="gpt-4o-mini-transcribe"):
        super().__init__(parent)
        self.credentials = credentials
        self.setWindowTitle("Settings")
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        info = QLabel("StudioNermi Cloud Lab 3.1.1 — Microphone Test Edition\nDark theme · Read-only files\n\n"
                      "OPENAI_API_KEY takes priority over session and keyring keys.\n"
                      "Enter a replacement key below; existing keys are never displayed.")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("OpenAI API key (leave blank to keep current key)")
        self.key_input.setAccessibleName("OpenAI API key")
        layout.addWidget(self.key_input)
        self.persist = QCheckBox("Save in system keyring (Linux Secret Service only)")
        layout.addWidget(self.persist)
        layout.addWidget(QLabel("OpenAI model"))
        self.model_input = QLineEdit(model)
        layout.addWidget(self.model_input)
        layout.addWidget(QLabel("Transcription model (session only)"))
        self.transcription_model_input = QLineEdit(transcription_model)
        layout.addWidget(self.transcription_model_input)
        self.status = QLabel("Keys stay in memory unless secure keyring storage is selected.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        forget = QPushButton("Forget session and saved key")
        forget.clicked.connect(self.forget)
        layout.addWidget(forget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.finished.connect(lambda _: self.key_input.clear())

    def save(self):
        if not self.model_input.text().strip() or not self.transcription_model_input.text().strip():
            self.status.setText("Enter both model names.")
            return
        key = self.key_input.text().strip()
        if key:
            try:
                self.credentials.save(key, self.persist.isChecked())
            except Exception:
                self.status.setText("Secure keyring unavailable or locked. Unlock it, or uncheck keyring storage to use a session key.")
                return
        self.accept()

    def forget(self):
        self.credentials.session_key = ''
        self.key_input.clear()
        try:
            self.credentials.forget()
            self.status.setText("Session and saved key removed. Environment variables are unchanged.")
        except Exception:
            self.status.setText("Session key cleared. Saved key could not be removed; check your system keyring. Environment variables are unchanged.")



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
        self.credentials = Credentials()
        self.ai_model = "gpt-4.1-mini"
        self.transcription_model = "gpt-4o-mini-transcribe"
        self.mic_test_worker = None
        self.voice_worker = None
        self.voice_cancelling = False
        self.history = []
        self.worker = None
        self.closing = False
        self.setWindowTitle("StudioNermi Cloud Lab 3.1.1 — Microphone Test Edition")
        self.resize(1400, 850)
        self.setMinimumSize(960, 640)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        header = QHBoxLayout()
        title = QLabel("StudioNermi Cloud Lab 3.1.1")
        title.setToolTip("StudioNermi Cloud Lab 3.1.1 — Microphone Test Edition")
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
        notice = QLabel(CLOUD_MESSAGE)
        notice.setWordWrap(True)
        assistant.addWidget(notice)
        self.chat = QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("Describe a project or ask a programming question.")
        assistant.addWidget(self.chat, 1)
        self.assistant_input = QLineEdit()
        self.assistant_input.setPlaceholderText("Type a message…")
        self.assistant_input.setAccessibleName("Message to AI assistant")
        assistant.addWidget(self.assistant_input)
        self.dictation_button = QPushButton("Start Dictation")
        self.dictation_button.setIcon(QIcon.fromTheme("audio-input-microphone"))
        self.dictation_button.setAccessibleName("Start Dictation")
        self.dictation_button.setToolTip("Record the default microphone. Stop to transcribe; audio is sent to OpenAI.")
        self.dictation_button.clicked.connect(self.toggle_dictation)
        self.cancel_dictation_button = QPushButton("Cancel Dictation")
        self.cancel_dictation_button.setEnabled(False)
        self.cancel_dictation_button.clicked.connect(self.cancel_dictation)
        voice_buttons = QHBoxLayout()
        voice_buttons.addWidget(self.dictation_button)
        self.test_microphone_button = QPushButton("Test Microphone")
        self.test_microphone_button.setAccessibleName("Test Microphone")
        self.test_microphone_button.setToolTip("Free offline test: record levels for up to five seconds. No audio is saved or uploaded.")
        self.test_microphone_button.clicked.connect(self.toggle_microphone_test)
        voice_buttons.addWidget(self.test_microphone_button)
        assistant.addLayout(voice_buttons)
        assistant.addWidget(self.cancel_dictation_button)
        self.mic_level = QProgressBar()
        self.mic_level.setRange(0, 100)
        self.mic_level.setValue(0)
        self.mic_level.setFormat("Microphone input level: %p%")
        self.mic_level.setAccessibleName("Live microphone input level")
        self.mic_level.hide()
        assistant.addWidget(self.mic_level)
        self.mic_test_status = QLabel("Offline microphone test · No API key or credits needed")
        self.mic_test_status.setWordWrap(True)
        assistant.addWidget(self.mic_test_status)
        self.voice_status = QLabel("Ready · Dictation records only when started (maximum 2 minutes)")
        self.voice_status.setWordWrap(True)
        assistant.addWidget(self.voice_status)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_request)
        self.ai_status = QLabel("Ready · Configure an API key in Settings or OPENAI_API_KEY")
        self.ai_status.setWordWrap(True)
        assistant.addWidget(self.ai_status)
        assistant.addWidget(self.stop_button)
        self.send_button = QPushButton("Send")
        assistant.addWidget(self.send_button)
        splitter.setSizes([260, 650, 360])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(QLabel("Local workspace  •  Files are previewed only  •  OpenAI API"))
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
            QPushButton:disabled { background: #202632; color: #8591a5; border-color: #354159; }
            QPushButton:hover:enabled { background: #3a4e70; }
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
        if not message or self.worker is not None or self.voice_worker is not None or self.mic_test_worker is not None:
            return
        key = self.credentials.resolve()
        if not key:
            self.ai_status.setText("No API key configured. Set OPENAI_API_KEY or open Settings.")
            return
        self.pending_message = message
        self.chat.appendPlainText(f"You: {message}\n")
        self.assistant_input.clear()
        self.ai_status.setText("Waiting for OpenAI…")
        self.send_button.setEnabled(False)
        self.dictation_button.setEnabled(False)
        self.test_microphone_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.settings_button.setEnabled(False)
        self.worker = AssistantWorker(key, self.ai_model,
            self.history + [{'role': 'user', 'content': message}], self)
        self.worker.succeeded.connect(self.receive_response)
        self.worker.failed.connect(self.request_failed)
        self.worker.cancelled.connect(lambda: self.request_failed("Request stopped. Remote processing may still incur charges."))
        self.worker.finished.connect(self.request_finished)
        self.worker.start()

    def receive_response(self, text):
        if self.worker._stop.is_set():
            self.request_failed("Request stopped. Remote processing may still incur charges.")
            return
        self.history.extend([{'role': 'user', 'content': self.pending_message},
                             {'role': 'assistant', 'content': text}])
        self.chat.appendPlainText(f"Assistant: {text}\n")
        self.ai_status.setText("Ready")

    def request_failed(self, message):
        self.ai_status.setText(message)
        self.chat.appendPlainText(f"Status: {message}\n")

    def stop_request(self):
        if self.worker:
            self.worker.stop()
            self.stop_button.setEnabled(False)
            self.ai_status.setText("Stopping request…")

    def request_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.send_button.setEnabled(True)
        self.dictation_button.setEnabled(True)
        self.test_microphone_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.settings_button.setEnabled(True)
        if self.closing:
            self.close()

    def closeEvent(self, event):
        if self.mic_test_worker is not None:
            self.closing = True
            self.mic_test_worker.stop()
            event.ignore()
        elif self.voice_worker is not None:
            self.closing = True
            self.cancel_dictation()
            event.ignore()
        elif self.worker is not None:
            self.closing = True
            self.stop_request()
            event.ignore()
        else:
            event.accept()

    def toggle_dictation(self):
        if self.voice_worker is not None:
            if self.dictation_button.isEnabled() and not self.voice_cancelling:
                self.voice_worker.finish_recording()
                self.dictation_button.setEnabled(False)
                self.voice_status.setText("Recording · Stopping microphone…")
            return
        if self.worker is not None or self.mic_test_worker is not None or self.closing:
            return
        key = self.credentials.resolve()
        if not key:
            self.voice_status.setText("Error · Configure an API key in Settings or OPENAI_API_KEY before dictating.")
            return
        self.voice_cancelling = False
        self.test_microphone_button.setEnabled(False)
        self.voice_status.setText("Recording · Opening default microphone…")
        self.dictation_button.setText("Stop Dictation")
        self.dictation_button.setAccessibleName("Stop Dictation")
        self.cancel_dictation_button.setEnabled(True)
        self.send_button.setEnabled(False)
        self.settings_button.setEnabled(False)
        self.voice_worker = VoiceWorker(key, self.transcription_model, self)
        self.voice_worker.recording.connect(self.voice_recording)
        self.voice_worker.transcribing.connect(self.voice_transcribing)
        self.voice_worker.succeeded.connect(self.receive_transcription)
        self.voice_worker.failed.connect(self.voice_error)
        self.voice_worker.cancelled.connect(self.voice_cancelled)
        self.voice_worker.finished.connect(self.voice_finished)
        self.voice_worker.start()

    def voice_recording(self):
        if not self.voice_cancelling:
            self.voice_status.setText("Recording · Speak now. Stop Dictation to transcribe, or Cancel Dictation.")

    def voice_transcribing(self):
        self.dictation_button.setEnabled(False)
        if not self.voice_cancelling:
            self.voice_status.setText("Transcribing · Audio is being sent to OpenAI…")

    def receive_transcription(self, text):
        if self.voice_cancelling:
            return
        existing = self.assistant_input.text()
        combined = existing + (" " if existing and not existing[-1].isspace() else "") + text
        # QLineEdit defaults to a 32,767 character limit; never silently truncate.
        self.assistant_input.setMaxLength(max(self.assistant_input.maxLength(), len(combined)))
        self.assistant_input.setText(combined)
        self.assistant_input.setFocus()
        self.voice_status.setText("Ready · Transcription added. Edit it, then press Send when ready.")

    def voice_error(self, message):
        if not self.voice_cancelling:
            self.voice_status.setText("Error · " + message)

    def voice_cancelled(self):
        self.voice_status.setText("Ready · Dictation cancelled. Remote processing may still incur charges.")

    def cancel_dictation(self):
        if self.voice_worker is not None:
            self.voice_cancelling = True
            self.voice_worker.stop()
            self.dictation_button.setEnabled(False)
            self.cancel_dictation_button.setEnabled(False)
            self.voice_status.setText("Ready · Cancelling dictation…")

    def voice_finished(self):
        self.voice_worker.deleteLater()
        self.voice_worker = None
        self.dictation_button.setText("Start Dictation")
        self.dictation_button.setAccessibleName("Start Dictation")
        self.dictation_button.setEnabled(True)
        self.cancel_dictation_button.setEnabled(False)
        self.test_microphone_button.setEnabled(True)
        self.send_button.setEnabled(True)
        self.settings_button.setEnabled(True)
        if self.closing:
            self.close()

    def toggle_microphone_test(self):
        if self.mic_test_worker is not None:
            self.mic_test_worker.stop()
            self.test_microphone_button.setEnabled(False)
            self.mic_test_status.setText("Stopping microphone test…")
            return
        if self.voice_worker is not None or self.worker is not None or self.closing:
            return
        # Intentionally no credentials lookup or API client on this path.
        self.mic_test_status.setText("Testing microphone · Speak now (up to five seconds). Offline only.")
        self.mic_level.setValue(0)
        self.mic_level.show()
        self.test_microphone_button.setText("Stop Test")
        self.test_microphone_button.setAccessibleName("Stop Test")
        self.dictation_button.setEnabled(False)
        self.send_button.setEnabled(False)
        self.settings_button.setEnabled(False)
        self.mic_test_worker = MicrophoneTestWorker(self)
        self.mic_test_worker.level.connect(self.mic_level.setValue)
        self.mic_test_worker.completed.connect(self.microphone_test_result)
        self.mic_test_worker.failed.connect(lambda message: self.mic_test_status.setText("Error · " + message))
        self.mic_test_worker.finished.connect(self.microphone_test_finished)
        self.mic_test_worker.start()

    def microphone_test_result(self, detected):
        self.mic_test_status.setText("Audio input detected · Offline test complete. No audio saved or uploaded."
            if detected else "No audio input detected · Microphone may be muted or too quiet. Check the default input, unmute it, and speak closer.")

    def microphone_test_finished(self):
        self.mic_test_worker.deleteLater()
        self.mic_test_worker = None
        self.mic_level.setValue(0)
        self.mic_level.hide()
        self.test_microphone_button.setText("Test Microphone")
        self.test_microphone_button.setAccessibleName("Test Microphone")
        self.test_microphone_button.setEnabled(True)
        self.dictation_button.setEnabled(True)
        self.send_button.setEnabled(True)
        self.settings_button.setEnabled(True)
        if self.closing:
            self.close()

    def show_settings(self):
        dialog = SettingsDialog(self.credentials, self.ai_model, self, self.transcription_model)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.ai_model = dialog.model_input.text().strip()
            self.transcription_model = dialog.transcription_model_input.text().strip()
            self.ai_status.setText("Settings updated · Ready to send")
        dialog.deleteLater()


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
