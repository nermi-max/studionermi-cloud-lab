"""Cloud behavior tested entirely with mocked SDK calls; no paid requests."""
import asyncio
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from openai import AuthenticationError, RateLimitError, APIConnectionError, APITimeoutError, PermissionDeniedError, APIStatusError
from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QLineEdit

from assistant import AssistantWorker, Credentials, error_message, SERVICE, ACCOUNT
from main import MainWindow, SettingsDialog


class CredentialTests(unittest.TestCase):
    def test_environment_session_keyring_precedence(self):
        creds = Credentials()
        creds.session_key = 'session-example'
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'env-example'}):
            self.assertEqual(creds.resolve(), 'env-example')
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            self.assertEqual(creds.resolve(), 'session-example')
            creds.session_key = ''
            with patch('assistant.secure_keyring') as backend:
                backend.return_value.get_password.return_value = 'saved-example'
                self.assertEqual(creds.resolve(), 'saved-example')
                backend.return_value.get_password.assert_called_with(SERVICE, ACCOUNT)
            with patch('assistant.secure_keyring', side_effect=RuntimeError('secret exception')):
                self.assertEqual(creds.resolve(), '')

    def test_session_storage_and_secure_save_failure(self):
        creds = Credentials()
        with patch('assistant.secure_keyring') as backend:
            creds.save('session-example')
            backend.assert_not_called()
            creds.save('saved-example', True)
            backend.return_value.set_password.assert_called_with(SERVICE, ACCOUNT, 'saved-example')
            creds.forget()
            backend.return_value.delete_password.assert_called_once()
            self.assertEqual(creds.session_key, '')
        with patch('assistant.secure_keyring', side_effect=RuntimeError()):
            with self.assertRaises(RuntimeError):
                creds.save('not-saved-example', True)
        self.assertEqual(creds.session_key, '')

    def test_reject_unknown_keyring_backend(self):
        with patch('keyring.get_keyring', return_value=MagicMock()):
            from assistant import secure_keyring
            with self.assertRaises(RuntimeError):
                secure_keyring()

    def test_friendly_errors_do_not_leak_exception_details(self):
        response = httpx.Response(401, request=httpx.Request('POST', 'https://api.openai.com/v1'))
        for cls, word in [(AuthenticationError, 'Authentication'), (RateLimitError, 'limit'),
                          (PermissionDeniedError, 'Access'), (APIStatusError, 'model')]:
            result = error_message(cls('sensitive-example', response=response, body=None))
            self.assertIn(word, result)
            self.assertNotIn('sensitive-example', result)
        for error, word in [(APIConnectionError(request=response.request), 'connect'),
                            (APITimeoutError(request=response.request), 'timed out'),
                            (ValueError('sensitive-example'), 'Settings')]:
            self.assertIn(word, error_message(error))
            self.assertNotIn('sensitive-example', error_message(error))


class CloudWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.credentials.session_key = 'test-placeholder'
        self.env = patch.dict(os.environ, {'OPENAI_API_KEY': ''})
        self.env.start()
        self.window.show()

    def tearDown(self):
        self.window.stop_request()
        self.wait_until(lambda: self.window.worker is None)
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.env.stop()

    def wait_until(self, condition):
        deadline = time.monotonic() + 4
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertTrue(condition())

    def sdk(self, create):
        client = MagicMock()
        client.chat.completions.create = create
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=client)
        manager.__aexit__ = AsyncMock(return_value=False)
        return patch('assistant.AsyncOpenAI', return_value=manager)

    def send(self, message='Help design a Python app'):
        self.window.assistant_input.setText(message)
        self.window.send_button.click()

    def test_success_sdk_arguments_and_conversation_context(self):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Suggested code: print(42)'))])
        create = AsyncMock(return_value=response)
        with self.sdk(create) as constructor:
            self.send()
            self.wait_until(lambda: self.window.worker is None)
            self.assertIn('Suggested code', self.window.chat.toPlainText())
            self.assertEqual(len(self.window.history), 2)
            self.send('Can you explain that?')
            self.wait_until(lambda: self.window.worker is None)
            kwargs = create.call_args.kwargs
            self.assertEqual(kwargs['model'], 'gpt-4.1-mini')
            self.assertEqual(kwargs['max_completion_tokens'], 2048)
            self.assertEqual([m['role'] for m in kwargs['messages']], ['system', 'user', 'assistant', 'user'])
            self.assertEqual(constructor.call_args.kwargs['base_url'], 'https://api.openai.com/v1')
            self.assertEqual(len(self.window.history), 4)
            self.assertTrue(self.window.send_button.isEnabled())
            self.assertFalse(self.window.stop_button.isEnabled())

    def test_stop_cancels_pending_request_and_ui_remains_responsive(self):
        cancelled = []
        async def slow(**kwargs):
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.append(True)
        with self.sdk(AsyncMock(side_effect=slow)):
            self.send()
            self.assertFalse(self.window.send_button.isEnabled())
            ticks = []
            QTimer.singleShot(20, lambda: ticks.append(True))
            self.wait_until(lambda: bool(ticks))
            self.window.stop_button.click()
            self.wait_until(lambda: self.window.worker is None)
            self.assertTrue(cancelled)
            self.assertIn('stopped', self.window.chat.toPlainText())
            self.assertEqual(self.window.history, [])

    def test_failure_and_retry(self):
        with self.sdk(AsyncMock(side_effect=ValueError('sensitive-example'))):
            self.send()
            self.wait_until(lambda: self.window.worker is None)
        self.assertNotIn('sensitive-example', self.window.chat.toPlainText())
        self.assertEqual(self.window.history, [])
        self.assertTrue(self.window.send_button.isEnabled())

    def test_authentication_error_reaches_ui_safely(self):
        response = httpx.Response(401, request=httpx.Request('POST', 'https://api.openai.com/v1'))
        error = AuthenticationError('sensitive-example', response=response, body=None)
        with self.sdk(AsyncMock(side_effect=error)):
            self.send()
            self.wait_until(lambda: self.window.worker is None)
        self.assertIn('Authentication failed', self.window.ai_status.text())
        self.assertNotIn('sensitive-example', self.window.chat.toPlainText())
        self.assertTrue(self.window.send_button.isEnabled())

    def test_settings_session_save(self):
        dialog = SettingsDialog(self.window.credentials, self.window.ai_model)
        dialog.key_input.setText('replacement-example')
        dialog.model_input.setText('gpt-4.1-mini')
        with patch('assistant.secure_keyring') as backend:
            dialog.save()
            backend.assert_not_called()
        self.assertEqual(self.window.credentials.session_key, 'replacement-example')
        self.assertEqual(dialog.key_input.text(), '')
        dialog.deleteLater()

    def test_close_during_request(self):
        async def slow(**kwargs):
            await asyncio.sleep(30)
        with self.sdk(AsyncMock(side_effect=slow)):
            self.send()
            self.window.close()
            self.wait_until(lambda: self.window.worker is None)
            self.assertFalse(self.window.isVisible())

    def test_settings_mask_cancel_and_failed_secure_save(self):
        dialog = SettingsDialog(self.window.credentials, self.window.ai_model)
        self.assertEqual(dialog.key_input.echoMode(), QLineEdit.EchoMode.Password)
        self.assertEqual(dialog.key_input.text(), '')
        dialog.key_input.setText('replacement-example')
        dialog.persist.setChecked(True)
        with patch('assistant.secure_keyring', side_effect=RuntimeError('sensitive-example')):
            dialog.save()
        self.assertIn('unavailable', dialog.status.text())
        self.assertNotIn('sensitive-example', dialog.status.text())
        self.assertEqual(self.window.credentials.session_key, 'test-placeholder')
        dialog.reject()
        self.assertEqual(dialog.key_input.text(), '')
        dialog.deleteLater()
