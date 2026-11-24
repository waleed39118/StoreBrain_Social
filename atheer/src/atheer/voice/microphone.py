"""Microphone capture with voice-activity detection (VAD) → whole utterances."""

from __future__ import annotations

import asyncio
import collections
import logging
from collections.abc import AsyncIterator

from atheer.voice.engines import SAMPLE_RATE

logger = logging.getLogger(__name__)

FRAME_MS = 30
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000 * 2  # int16 mono


class VadSegmenter:
    """Turns a stream of 30 ms frames into utterances.

    An utterance starts after ``start_ms`` of speech (with ``pre_roll_ms`` of
    audio kept so the first syllable isn't clipped) and ends after
    ``silence_ms`` of silence or at ``max_ms``.
    """

    def __init__(
        self,
        aggressiveness: int = 2,
        *,
        start_ms: int = 150,
        silence_ms: int = 700,
        pre_roll_ms: int = 300,
        max_ms: int = 15_000,
    ) -> None:
        import webrtcvad  # lazy: optional dependency

        self._vad = webrtcvad.Vad(aggressiveness)
        self._start = start_ms // FRAME_MS
        self._silence = silence_ms // FRAME_MS
        self._max = max_ms // FRAME_MS
        self._ring: collections.deque[tuple[bytes, bool]] = collections.deque(maxlen=pre_roll_ms // FRAME_MS)
        self._voiced: list[bytes] = []
        self._in_speech = False
        self._silent_run = 0

    def push(self, frame: bytes) -> bytes | None:
        """Feed one frame; returns a complete utterance (PCM16) when one ends."""
        speech = self._vad.is_speech(frame, SAMPLE_RATE)
        if not self._in_speech:
            self._ring.append((frame, speech))
            if sum(1 for _, s in self._ring if s) >= self._start:
                self._in_speech = True
                self._voiced = [f for f, _ in self._ring]
                self._ring.clear()
            return None

        self._voiced.append(frame)
        self._silent_run = 0 if speech else self._silent_run + 1
        if self._silent_run >= self._silence or len(self._voiced) >= self._max:
            utterance = b"".join(self._voiced)
            self._voiced, self._in_speech, self._silent_run = [], False, 0
            return utterance
        return None


async def microphone_utterances(segmenter: VadSegmenter | None = None) -> AsyncIterator[bytes]:
    """Yield utterances from the default microphone until cancelled."""
    import sounddevice as sd  # lazy: optional dependency

    loop = asyncio.get_running_loop()
    frames: asyncio.Queue[bytes] = asyncio.Queue(maxsize=500)
    segmenter = segmenter or VadSegmenter()

    def _callback(indata, _frames, _time, status) -> None:  # runs on the audio thread
        if status:
            logger.warning("Audio input status: %s", status)
        try:
            loop.call_soon_threadsafe(frames.put_nowait, bytes(indata))
        except asyncio.QueueFull:
            logger.warning("Audio frame dropped (consumer too slow)")

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE, blocksize=FRAME_BYTES // 2, channels=1, dtype="int16", callback=_callback
    ):
        while True:
            utterance = segmenter.push(await frames.get())
            if utterance:
                yield utterance
