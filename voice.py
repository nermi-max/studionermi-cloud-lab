"""Explicit, bounded microphone capture. Audio stays in memory, never on disk."""
import asyncio
import io
import wave
import threading
import time

from openai import AsyncOpenAI
from PySide6.QtCore import Signal

from assistant import AssistantWorker, error_message

SAMPLE_RATE = 16000
MAX_SECONDS = 120
MAX_BYTES = SAMPLE_RATE * 2 * MAX_SECONDS
MICROPHONE_ERROR = ('Cannot record from the default microphone. Check microphone permission, '
                    'the default input and mute settings in MATE Sound/PulseAudio Volume Control, '
                    'and that PipeWire/PulseAudio and PortAudio are available.')


class VoiceWorker(AssistantWorker):
    recording = Signal()
    transcribing = Signal()

    def __init__(self, key, model, parent=None):
        super().__init__(key, model, [], parent)
        self._recording_done = threading.Event()
        self.audio = bytearray()

    def finish_recording(self):
        self._recording_done.set()

    def capture(self):
        import sounddevice as sd
        overflow = threading.Event()

        def callback(data, frames, timing, status):
            if self._stop.is_set() or self._recording_done.is_set():
                return
            if status:
                overflow.set()
                self._recording_done.set()
                return
            remaining = MAX_BYTES - len(self.audio)
            self.audio.extend(bytes(data)[:remaining])
            if len(self.audio) >= MAX_BYTES:
                self._recording_done.set()

        # PortAudio uses the system default input, including PulseAudio/PipeWire
        # through the Linux default ALSA device. Do not choose an arbitrary device.
        with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16',
                               callback=callback) as stream:
            deadline = time.monotonic() + MAX_SECONDS
            self.recording.emit()
            while not self._recording_done.wait(.05):
                if self._stop.is_set() or time.monotonic() >= deadline:
                    break
                if not stream.active:
                    raise RuntimeError("Microphone disconnected")
        if overflow.is_set():
            raise RuntimeError('Audio capture failed')

    async def request(self):
        with io.BytesIO() as wav:
            with wave.open(wav, 'wb') as recording:
                recording.setnchannels(1)
                recording.setsampwidth(2)
                recording.setframerate(SAMPLE_RATE)
                recording.writeframes(self.audio)
            wav.seek(0)
            async with AsyncOpenAI(api_key=self._key, base_url='https://api.openai.com/v1',
                                   timeout=60.0, max_retries=0) as client:
                result = await client.audio.transcriptions.create(
                    model=self.model, file=('dictation.wav', wav, 'audio/wav'))
                return result.text.strip()

    def run(self):
        try:
            try:
                if not self._stop.is_set():
                    self.capture()
            except Exception:
                if not self._stop.is_set():
                    self.failed.emit(MICROPHONE_ERROR)
                    return
            if self._stop.is_set():
                self.cancelled.emit()
                return
            if not self.audio:
                self.failed.emit('No audio captured. Check your microphone and try again.')
                return
            self.transcribing.emit()
            result = asyncio.run(self.run_request())
            if self._stop.is_set():
                self.cancelled.emit()
            elif result:
                self.succeeded.emit(result)
            else:
                self.failed.emit('No speech recognized. Try speaking clearly and record again.')
        except asyncio.CancelledError:
            self.cancelled.emit()
        except Exception as error:
            if self._stop.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(error_message(error))
        finally:
            self.audio.clear()
            self._key = ''
