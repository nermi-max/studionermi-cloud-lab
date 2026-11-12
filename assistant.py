"""Cloud requests and credentials. Never log credentials or raw API exceptions."""
import asyncio
import os
import logging
import threading

from openai import (AsyncOpenAI, APIConnectionError, APITimeoutError,
                    AuthenticationError, PermissionDeniedError, RateLimitError, APIStatusError)
from PySide6.QtCore import QThread, Signal

# Suppress SDK/HTTP diagnostics, including environment-enabled debug output.
# User-facing failures are mapped to fixed messages below.
for logger_name in ('openai', 'httpx', 'httpcore'):
    logger = logging.getLogger(logger_name)
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False

SERVICE = 'StudioNermi Cloud Lab'
ACCOUNT = 'openai-api-key'
SYSTEM_PROMPT = ('You are a helpful coding assistant. Answer programming questions and help plan '
                 'software projects. You cannot access local files, execute code, or change files. '
                 'Present code as suggestions for the user to review.')


def secure_keyring():
    """Only accept Linux Secret Service, never plaintext or unknown fallback backends."""
    import keyring
    from keyring.backends.SecretService import Keyring
    backend = keyring.get_keyring()
    if type(backend) is not Keyring:
        raise RuntimeError('Secure Secret Service keyring unavailable')
    return backend


class Credentials:
    def __init__(self):
        self.session_key = ''

    def resolve(self):
        key = os.environ.get('OPENAI_API_KEY', '').strip() or self.session_key
        if key:
            return key
        try:
            return secure_keyring().get_password(SERVICE, ACCOUNT) or ''
        except Exception:
            return ''

    def save(self, key, persist=False):
        if persist:
            secure_keyring().set_password(SERVICE, ACCOUNT, key)
        self.session_key = key

    def forget(self):
        secure_keyring().delete_password(SERVICE, ACCOUNT)
        self.session_key = ''


def error_message(error):
    if isinstance(error, AuthenticationError):
        return 'Authentication failed. Check your OpenAI API key in Settings or OPENAI_API_KEY.'
    if isinstance(error, RateLimitError):
        return 'API usage limit reached. Check your API credits, billing, and rate limits before retrying.'
    if isinstance(error, APITimeoutError):
        return 'The request timed out. Please try again.'
    if isinstance(error, APIConnectionError):
        return 'Cannot connect to OpenAI. Check your internet connection and try again.'
    if isinstance(error, PermissionDeniedError):
        return 'Access denied. Check your API project permissions and model access.'
    if isinstance(error, APIStatusError):
        return 'OpenAI could not complete the request. Check the model in Settings and try again later.'
    return 'The request could not be completed. Check Settings and try again.'


class AssistantWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, key, model, messages, parent=None):
        super().__init__(parent)
        self._key = key
        self.model = model
        self.messages = messages
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    async def request(self):
        # Fixed official endpoint; do not inherit OPENAI_BASE_URL or SDK debug logging.
        async with AsyncOpenAI(api_key=self._key, base_url='https://api.openai.com/v1',
                               timeout=60.0, max_retries=0) as client:
            result = await client.chat.completions.create(
                model=self.model, messages=[{'role': 'system', 'content': SYSTEM_PROMPT}] + self.messages,
                max_completion_tokens=2048)
            return result.choices[0].message.content or 'The model returned no text. Please rephrase your question.'

    async def run_request(self):
        task = asyncio.create_task(self.request())
        try:
            while not task.done():
                if self._stop.is_set():
                    task.cancel()
                    break
                await asyncio.wait({task}, timeout=0.05)
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def run(self):
        try:
            result = asyncio.run(self.run_request())
            if self._stop.is_set():
                self.cancelled.emit()
            else:
                self.succeeded.emit(result)
        except asyncio.CancelledError:
            self.cancelled.emit()
        except Exception as error:
            if self._stop.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(error_message(error))
        finally:
            self._key = ''
