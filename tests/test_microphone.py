"""Offline test uses synthetic PCM and a mocked PortAudio module only."""
import array
import time
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication

from main import MainWindow
from voice import MicrophoneTestWorker, SAMPLE_RATE


class MicrophoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.samples = array.array('h', [1000] * 800).tobytes()
        self.closed = False
        self.opened = 0
        self.callback = None
        self.backend = MagicMock()
        self.backend.RawInputStream.side_effect = self.stream
        self.module_patch = patch.dict('sys.modules', {'sounddevice': self.backend})
        self.module_patch.start()
        # Offline test must not resolve credentials, contact API, or encode a WAV.
        self.patches = [patch.object(self.window.credentials, 'resolve', side_effect=AssertionError('No credentials allowed')),
                        patch('voice.AsyncOpenAI', side_effect=AssertionError('No API allowed')),
                        patch('assistant.AsyncOpenAI', side_effect=AssertionError('No API allowed')),
                        patch('voice.wave.open', side_effect=AssertionError('No recording allowed'))]
        for item in self.patches:
            item.start()

    def stream(self, **kwargs):
        self.opened += 1
        self.assertEqual(kwargs['samplerate'], SAMPLE_RATE)
        self.assertEqual(kwargs['channels'], 1)
        self.assertEqual(kwargs['dtype'], 'int16')
        self.assertNotIn('device', kwargs)
        self.callback = kwargs['callback']
        owner = self
        class Stream:
            active = True
            def __enter__(self):
                owner.callback(owner.samples, len(owner.samples) // 2, None, False)
                return self
            def __exit__(self, *args):
                owner.closed = True
        return Stream()

    def wait_until(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertTrue(predicate())

    def tearDown(self):
        if self.window.mic_test_worker:
            self.window.mic_test_worker.stop()
        self.wait_until(lambda: self.window.mic_test_worker is None)
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        for item in reversed(self.patches):
            item.stop()
        self.module_patch.stop()

    def test_no_automatic_capture(self):
        self.assertIsNone(self.window.mic_test_worker)
        self.backend.RawInputStream.assert_not_called()
        self.assertFalse(self.window.mic_level.isVisible())

    def test_live_level_early_stop_and_offline_detection(self):
        self.window.assistant_input.setText('Keep this input')
        self.window.test_microphone_button.click()
        worker = self.window.mic_test_worker
        self.wait_until(lambda: self.window.mic_level.value() > 0)
        self.assertTrue(self.window.mic_level.isVisible())
        self.assertEqual(self.window.test_microphone_button.text(), 'Stop Test')
        self.assertFalse(self.window.dictation_button.isEnabled())
        tick = []
        QTimer.singleShot(10, lambda: tick.append(True))
        self.wait_until(lambda: bool(tick))
        self.window.toggle_dictation()
        self.assertIsNone(self.window.voice_worker)
        self.window.send_message()
        self.assertEqual(self.window.chat.toPlainText(), '')
        self.window.test_microphone_button.click()
        self.wait_until(lambda: self.window.mic_test_worker is None)
        self.assertEqual(self.opened, 1)
        self.assertTrue(self.closed)
        self.assertIn('Audio input detected', self.window.mic_test_status.text())
        self.assertFalse(hasattr(worker, 'audio'))
        self.assertEqual(self.window.assistant_input.text(), 'Keep this input')
        self.assertEqual(self.window.test_microphone_button.text(), 'Test Microphone')
        self.assertTrue(self.window.dictation_button.isEnabled())
        self.assertFalse(self.window.mic_level.isVisible())

    def test_silence_auto_finishes_with_muted_guidance(self):
        self.samples = bytes(1600)
        with patch.object(MicrophoneTestWorker, 'DURATION', .12):
            self.window.test_microphone_button.click()
            self.wait_until(lambda: self.window.mic_test_worker is None)
        self.assertTrue(self.closed)
        self.assertIn('No audio input detected', self.window.mic_test_status.text())
        self.assertIn('muted', self.window.mic_test_status.text())

    def test_five_second_frame_limit(self):
        self.assertEqual(MicrophoneTestWorker.DURATION, 5.0)
        self.samples = array.array('h', [2000] * (5 * SAMPLE_RATE)).tobytes()
        self.window.test_microphone_button.click()
        self.wait_until(lambda: self.window.mic_test_worker is None)
        self.assertIn('Audio input detected', self.window.mic_test_status.text())
        self.assertTrue(self.closed)

    def test_device_error_safe_and_can_retry(self):
        self.backend.RawInputStream.side_effect = OSError('private device details')
        self.window.test_microphone_button.click()
        self.wait_until(lambda: self.window.mic_test_worker is None)
        text = self.window.mic_test_status.text()
        self.assertIn('Error', text)
        self.assertIn('permission', text)
        self.assertNotIn('private device details', text)
        self.assertTrue(self.window.test_microphone_button.isEnabled())
        self.backend.RawInputStream.side_effect = self.stream
        with patch.object(MicrophoneTestWorker, 'DURATION', .1):
            self.window.test_microphone_button.click()
            self.wait_until(lambda: self.window.mic_test_worker is None)
        self.assertIn('Audio input detected', self.window.mic_test_status.text())

    def test_capture_overflow_fails_and_closes_stream(self):
        self.window.test_microphone_button.click()
        self.wait_until(lambda: self.callback is not None)
        self.callback(self.samples, 800, None, True)
        self.wait_until(lambda: self.window.mic_test_worker is None)
        self.assertIn('Error', self.window.mic_test_status.text())
        self.assertTrue(self.closed)

    def test_close_during_test(self):
        self.window.test_microphone_button.click()
        self.wait_until(lambda: self.callback is not None)
        self.window.close()
        self.wait_until(lambda: self.window.mic_test_worker is None)
        self.assertFalse(self.window.isVisible())
        self.assertTrue(self.closed)

    def test_blocked_while_dictation_active(self):
        self.window.voice_worker = object()
        try:
            self.window.toggle_microphone_test()
            self.assertIsNone(self.window.mic_test_worker)
            self.backend.RawInputStream.assert_not_called()
        finally:
            self.window.voice_worker = None
