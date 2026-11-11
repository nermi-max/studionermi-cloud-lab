"""Headless interaction tests; run with QT_QPA_PLATFORM=offscreen."""

import unittest
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from main import MainWindow


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_window_and_buttons(self):
        self.assertEqual(self.window.windowTitle(), "StudioNermi Cloud Lab")
        self.assertTrue(self.window.isVisible())
        self.assertEqual(
            [b.text() for b in (self.window.open_button,
                               self.window.settings_button, self.window.exit_button)],
            ["Open File", "Settings", "Exit"],
        )

    def test_open_file(self):
        with patch("main.QFileDialog.getOpenFileName", return_value=("/tmp/example.txt", "")):
            self.window.open_button.click()
        self.assertEqual(self.window.file_label.text(), "Selected file: example.txt")
        self.assertEqual(self.window.file_label.toolTip(), "/tmp/example.txt")

    def test_cancel_preserves_selection(self):
        with patch("main.QFileDialog.getOpenFileName", return_value=("", "")):
            self.window.open_button.click()
        self.assertEqual(self.window.file_label.text(), "No file selected")

    def test_settings_dialog(self):
        observed = []

        def dismiss():
            dialog = self.app.activeModalWidget()
            if dialog:
                observed.append((dialog.windowTitle(), dialog.text()))
                dialog.accept()

        QTimer.singleShot(0, dismiss)
        self.window.settings_button.click()
        self.assertEqual(observed[0][0], "Settings")
        self.assertIn("dark theme", observed[0][1])

    def test_exit(self):
        self.window.exit_button.click()
        self.app.processEvents()
        self.assertFalse(self.window.isVisible())


if __name__ == "__main__":
    unittest.main()
