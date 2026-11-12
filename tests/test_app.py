"""Real Qt widget tests; run with QT_QPA_PLATFORM=offscreen."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication

from PySide6.QtWidgets import QLineEdit

def dialog_password_mode():
    return QLineEdit.EchoMode.Password


from main import MainWindow, MAX_PREVIEW_BYTES, CLOUD_MESSAGE, PythonHighlighter


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.file = self.root / 'sample.py'
        self.file.write_text('import pathlib\nraise RuntimeError("never run")\n', encoding='utf-8')
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()

    def test_window_and_read_only_controls(self):
        self.assertEqual(self.window.windowTitle(), 'StudioNermi Cloud Lab 3.1 — Voice Edition')
        self.assertTrue(self.window.preview.isReadOnly())
        self.assertTrue(self.window.model.isReadOnly())
        self.assertTrue(self.window.chat.isReadOnly())
        self.assertEqual(self.window.project_button.text(), 'Open Project')

    def test_open_project_and_select_file_without_execution(self):
        (self.root / 'nested').mkdir()
        with patch('main.QFileDialog.getExistingDirectory', return_value=str(self.root)):
            self.window.project_button.click()
        self.assertEqual(self.window.project_path, self.root)
        self.assertEqual(self.window.model.filePath(self.window.tree.rootIndex()), str(self.root))
        index = self.window.model.index(str(self.file))
        self.assertTrue(index.isValid())
        self.window.tree.setCurrentIndex(index)
        self.app.processEvents()
        self.assertEqual(self.window.preview.toPlainText(), self.file.read_text())
        self.assertTrue(self.window.model.isDir(self.window.model.index(str(self.root / 'nested'))))

    def test_open_file_preserved(self):
        with patch('main.QFileDialog.getOpenFileName', return_value=(str(self.file), '')):
            self.window.open_button.click()
        self.assertEqual(self.window.file_label.text(), 'Selected file: sample.py')
        self.assertEqual(self.window.file_label.toolTip(), str(self.file))
        self.assertEqual(self.window.preview.toPlainText(), self.file.read_text())

    def test_cancel_preserves_project_and_preview(self):
        with patch('main.QFileDialog.getExistingDirectory', return_value=str(self.root)):
            self.window.open_project()
        self.window.preview_file(self.file)
        with patch('main.QFileDialog.getExistingDirectory', return_value=''), patch(
                'main.QFileDialog.getOpenFileName', return_value=('', '')):
            self.window.open_project()
            self.window.open_file()
        self.assertEqual(self.window.project_path, self.root)
        self.assertEqual(self.window.preview.toPlainText(), self.file.read_text())

    def test_preview_errors_replace_old_contents(self):
        for name, data, expected in [
            ('binary.bin', b'\0abc', 'Binary'),
            ('large.txt', b'x' * (MAX_PREVIEW_BYTES + 1), 'too large'),
            ('invalid.txt', b'\xff', 'UTF-8'),
        ]:
            with self.subTest(name=name):
                path = self.root / name
                path.write_bytes(data)
                self.window.preview_file(path)
                self.assertIn(expected, self.window.preview.toPlainText())
        self.window.preview_file(self.root / 'missing.py')
        self.assertIn('Preview unavailable', self.window.preview.toPlainText())
        self.window.preview_file(self.root)
        self.assertIn('regular file', self.window.preview.toPlainText())

    def test_python_highlighting_and_plain_text_switch(self):
        self.window.preview_file(self.file)
        self.window.highlighter.rehighlight()
        self.assertTrue(self.window.preview.document().firstBlock().layout().formats())
        plain = self.root / 'notes.txt'
        plain.write_text('import pathlib')
        self.window.preview_file(plain)
        self.assertFalse(self.window.preview.document().firstBlock().layout().formats())
        self.window.preview_file(self.file)
        self.window.highlighter.rehighlight()
        self.assertTrue(self.window.preview.document().firstBlock().layout().formats())

    def test_multiline_highlighting(self):
        document = QTextDocument('"""hello\nstill a string\nend"""\nreturn 42 # comment')
        highlighter = PythonHighlighter(document)
        highlighter.rehighlight()
        self.assertEqual(document.firstBlock().userState(), 2)
        self.assertEqual(document.findBlockByNumber(1).userState(), 2)
        self.assertEqual(document.findBlockByNumber(2).userState(), 0)
        self.assertGreaterEqual(len(document.lastBlock().layout().formats()), 3)

    def test_assistant_missing_key_and_empty_message(self):
        self.window.send_button.click()
        self.assertEqual(self.window.chat.toPlainText(), '')
        self.window.assistant_input.setText('Explain this file')
        with patch.object(self.window.credentials, 'resolve', return_value=''):
            self.window.send_button.click()
        self.assertIn('No API key', self.window.ai_status.text())
        self.assertIsNone(self.window.worker)
        self.assertEqual(self.window.assistant_input.text(), 'Explain this file')

    def test_settings_dialog(self):
        observed = []

        def dismiss():
            dialog = self.app.activeModalWidget()
            observed.append((dialog.windowTitle(), dialog.key_input.echoMode()))
            dialog.accept()

        QTimer.singleShot(0, dismiss)
        self.window.settings_button.click()
        self.assertEqual(observed[0][0], 'Settings')
        self.assertEqual(observed[0][1], dialog_password_mode())

    def test_exit(self):
        self.window.exit_button.click()
        self.app.processEvents()
        self.assertFalse(self.window.isVisible())


if __name__ == '__main__':
    unittest.main()
