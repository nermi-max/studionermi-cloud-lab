"""All microphone and transcription calls are mocked; no hardware or paid calls."""
import asyncio
import io
import time
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication

from main import MainWindow, SettingsDialog
from voice import VoiceWorker, MICROPHONE_ERROR, MAX_BYTES


class VoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.key = patch.object(self.window.credentials, 'resolve', return_value='test-placeholder')
        self.key.start()
        self.window.show()
        self.audio = bytearray(b'\0\1' * 160)
        self.stream_closed = False
        self.sdk_calls = []
        self.create = AsyncMock(side_effect=self.response)
        client = MagicMock()
        client.audio.transcriptions.create = self.create
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=client)
        manager.__aexit__ = AsyncMock(return_value=False)
        self.sdk = patch('voice.AsyncOpenAI', return_value=manager)
        self.sdk.start()
        self.audio_module = patch.dict("sys.modules", {"sounddevice": MagicMock()})
        self.audio_module.start()
        self.stream_patch = patch('sounddevice.RawInputStream', side_effect=self.stream)
        self.stream_patch.start()

    async def response(self, **kwargs):
        name, file, mime = kwargs['file']
        with wave.open(io.BytesIO(file.read()), 'rb') as wav:
            self.sdk_calls.append((kwargs['model'], name, mime, wav.getnchannels(), wav.getframerate()))
        return SimpleNamespace(text=' Add a Python API. ')

    def stream(self, **kwargs):
        self.assertEqual(kwargs['channels'], 1)
        self.assertEqual(kwargs['dtype'], 'int16')
        self.assertNotIn('device', kwargs)  # System default, no arbitrary input.
        owner = self
        class Stream:
            active = True
            def __enter__(self):
                kwargs['callback'](owner.audio, 160, None, False)
                return self
            def __exit__(self, *args):
                owner.stream_closed = True
        return Stream()

    def wait_until(self, condition):
        deadline = time.monotonic() + 4
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertTrue(condition())

    def start(self):
        self.window.dictation_button.click()
        self.wait_until(lambda: 'Speak now' in self.window.voice_status.text())
        return self.window.voice_worker

    def tearDown(self):
        self.window.cancel_dictation()
        self.wait_until(lambda: self.window.voice_worker is None)
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.key.stop()
        self.sdk.stop()
        self.stream_patch.stop()
        self.audio_module.stop()

    def test_stop_transcribes_appends_latest_text_without_sending(self):
        self.window.assistant_input.setText('Already typed.')
        worker = self.start()
        self.assertFalse(self.window.send_button.isEnabled())
        self.assertEqual(self.window.dictation_button.text(), 'Stop Dictation')
        self.window.assistant_input.setText('Edited while recording.')
        self.window.dictation_button.click()
        self.wait_until(lambda: self.window.voice_worker is None)
        self.assertEqual(self.window.assistant_input.text(), 'Edited while recording. Add a Python API.')
        self.assertEqual(self.window.chat.toPlainText(), '')
        self.assertEqual(self.window.history, [])
        self.assertEqual(self.sdk_calls, [('gpt-4o-mini-transcribe', 'dictation.wav', 'audio/wav', 1, 16000)])
        self.assertTrue(self.stream_closed)
        self.assertEqual(worker.audio, bytearray())
        self.assertTrue(self.window.send_button.isEnabled())
        self.assertIn('Ready', self.window.voice_status.text())
        self.window.assistant_input.setText('User edited transcript')
        self.assertEqual(self.window.assistant_input.text(), 'User edited transcript')

    def test_cancel_recording_and_no_overlap(self):
        self.window.assistant_input.setText('Keep this')
        worker = self.start()
        self.window.toggle_dictation()  # Stops this session, never starts another.
        self.assertIs(self.window.voice_worker, worker)
        self.window.cancel_dictation_button.click()
        self.wait_until(lambda: self.window.voice_worker is None)
        self.assertEqual(self.window.assistant_input.text(), 'Keep this')
        self.assertEqual(worker.audio, bytearray())
        self.assertEqual(self.window.dictation_button.text(), 'Start Dictation')
        self.assertIn('cancelled', self.window.voice_status.text())

    def test_cancel_during_transcription_and_responsive_ui(self):
        cancelled = []
        async def slow(**kwargs):
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.append(True)
        self.create.side_effect = slow
        worker = self.start()
        self.window.dictation_button.click()
        self.wait_until(lambda: 'Transcribing' in self.window.voice_status.text())
        tick = []
        QTimer.singleShot(20, lambda: tick.append(True))
        self.wait_until(lambda: bool(tick))
        self.window.cancel_dictation()
        self.wait_until(lambda: self.window.voice_worker is None)
        self.assertTrue(cancelled)
        self.assertEqual(worker.audio, bytearray())
        self.assertEqual(self.window.assistant_input.text(), '')

    def test_device_error_is_safe_and_preserves_text(self):
        self.window.assistant_input.setText('Keep this')
        with patch('sounddevice.RawInputStream', side_effect=RuntimeError('private details')):
            self.window.dictation_button.click()
            self.wait_until(lambda: self.window.voice_worker is None)
        self.assertIn(MICROPHONE_ERROR, self.window.voice_status.text())
        self.assertIn('Error', self.window.voice_status.text())
        self.assertNotIn('private details', self.window.voice_status.text())
        self.assertEqual(self.window.assistant_input.text(), 'Keep this')
        self.create.assert_not_called()

    def test_api_error_and_empty_transcript_cleanup(self):
        for side_effect in (ValueError('private details'), None):
            with self.subTest(side_effect=side_effect):
                self.create.side_effect = side_effect
                self.create.return_value = SimpleNamespace(text='')
                worker = self.start()
                self.window.dictation_button.click()
                self.wait_until(lambda: self.window.voice_worker is None)
                self.assertIn('Error', self.window.voice_status.text())
                self.assertNotIn('private details', self.window.voice_status.text())
                self.assertEqual(worker.audio, bytearray())

    def test_close_cancels_recording(self):
        worker = self.start()
        self.window.close()
        self.wait_until(lambda: self.window.voice_worker is None)
        self.assertFalse(self.window.isVisible())
        self.assertEqual(worker.audio, bytearray())
        self.create.assert_not_called()

    def test_missing_key_does_not_open_microphone(self):
        with patch.object(self.window.credentials, 'resolve', return_value=''):
            self.window.dictation_button.click()
        self.assertIsNone(self.window.voice_worker)
        self.assertIn('Error', self.window.voice_status.text())

    def test_model_setting_and_recording_limit(self):
        dialog = SettingsDialog(self.window.credentials, self.window.ai_model)
        dialog.transcription_model_input.setText('whisper-1')
        dialog.save()
        self.assertEqual(dialog.transcription_model_input.text(), 'whisper-1')
        dialog.deleteLater()
        self.window.transcription_model = 'whisper-1'
        self.audio = bytearray(MAX_BYTES + 100)
        self.window.dictation_button.click()
        self.wait_until(lambda: self.window.voice_worker is None)
        self.assertEqual(self.sdk_calls[0][0], 'whisper-1')
        self.assertTrue(self.stream_closed)

    def test_empty_capture_does_not_upload(self):
        self.audio.clear()
        worker = self.start()
        self.window.dictation_button.click()
        self.wait_until(lambda: self.window.voice_worker is None)
        self.create.assert_not_called()
        self.assertIn('No audio captured', self.window.voice_status.text())
        self.assertEqual(worker.audio, bytearray())

    def test_no_automatic_recording(self):
        self.assertIsNone(self.window.voice_worker)
        self.assertEqual(self.window.dictation_button.text(), 'Start Dictation')
        self.create.assert_not_called()
