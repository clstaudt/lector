"""Audio player — buffer management, sounddevice playback, on-demand TTS generation."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    from kokoro_onnx import Kokoro


class AudioPlayer:
    """Manages audio buffer, on-demand TTS generation, and playback.

    A background worker generates chunks just ahead of the playback
    cursor (look-ahead).  When speed changes the worker discards
    pre-generated audio after the current chunk and re-generates at the
    new speed.
    """

    SPEED_STEP = 0.1
    SPEED_MIN = 0.5
    SPEED_MAX = 2.0
    LOOK_AHEAD = 3

    def __init__(
        self,
        sample_rate: int = 24000,
        voice: str = "",
        speed: float = 1.0,
        lang: str = "",
        *,
        engine: Kokoro | None = None,
        voice_style: np.ndarray | None = None,
        phoneme_batches: list[str] | None = None,
    ) -> None:
        self.sample_rate = sample_rate

        # Metadata (for display)
        self.voice = voice
        self.speed = speed
        self.lang = lang

        # Generation resources
        self._engine = engine
        self._voice_style = voice_style
        self._phoneme_batches: list[str] = phoneme_batches or []
        self._expected_chunks: int = len(self._phoneme_batches)

        # Audio buffer (grows as chunks arrive, kept in memory only)
        self._buffer = np.empty(0, dtype=np.float32)
        self._lock = threading.Lock()

        # Chunk boundary tracking — sample offset where each chunk starts.
        self._chunk_starts: list[int] = []

        # Playback state
        self._play_pos: int = 0
        self._paused = False
        self._stopped = False

        # Generation state
        self._gen_cursor: int = 0
        self._chunks_received: int = 0
        self._generation_done = False
        self._gen_epoch: int = 0
        self._gen_wakeup = threading.Event()

        self._stream: sd.OutputStream | None = None

    # -- generation ---------------------------------------------------------

    def start_generation(self) -> None:
        """Start the background generation worker thread."""
        t = threading.Thread(target=self._generation_worker, daemon=True)
        t.start()

    def _generation_worker(self) -> None:
        while not self._stopped:
            current = self.current_chunk_index
            cursor = self._gen_cursor

            if cursor >= self._expected_chunks:
                self._generation_done = True
                break

            if cursor - current >= self.LOOK_AHEAD:
                self._gen_wakeup.wait(timeout=0.3)
                self._gen_wakeup.clear()
                continue

            epoch = self._gen_epoch
            batch = self._phoneme_batches[cursor]
            audio, _ = self._engine._create_audio(
                batch, self._voice_style, self.speed,
            )

            with self._lock:
                if epoch != self._gen_epoch:
                    continue
                self._chunk_starts.append(len(self._buffer))
                self._buffer = np.concatenate([self._buffer, audio])
                self._chunks_received += 1
                self._gen_cursor += 1

        if not self._stopped:
            self._generation_done = True

    # -- transport controls -------------------------------------------------

    def start(self) -> None:
        """Open the audio output stream and begin playback."""
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._callback,
            blocksize=2048,
        )
        self._stream.start()

    def stop(self) -> None:
        """Stop playback and generation."""
        self._stopped = True
        self._gen_wakeup.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def toggle_pause(self) -> None:
        self._paused = not self._paused

    def next_chunk(self) -> None:
        """Jump to the start of the next sentence chunk."""
        with self._lock:
            for start in self._chunk_starts:
                if start > self._play_pos:
                    self._play_pos = start
                    break
            else:
                self._play_pos = len(self._buffer)
        self._gen_wakeup.set()

    def prev_chunk(self) -> None:
        """Jump back to current or previous sentence chunk."""
        with self._lock:
            grace = int(0.5 * self.sample_rate)
            for start in reversed(self._chunk_starts):
                if start < self._play_pos - grace:
                    self._play_pos = start
                    return
            self._play_pos = 0

    def restart(self) -> None:
        """Restart playback from the beginning."""
        with self._lock:
            self._play_pos = 0
            self._paused = False

    def speed_up(self) -> None:
        old = self.speed
        self.speed = round(min(self.speed + self.SPEED_STEP, self.SPEED_MAX), 1)
        if self.speed != old:
            self._invalidate_future_chunks()

    def speed_down(self) -> None:
        old = self.speed
        self.speed = round(max(self.speed - self.SPEED_STEP, self.SPEED_MIN), 1)
        if self.speed != old:
            self._invalidate_future_chunks()

    def _invalidate_future_chunks(self) -> None:
        """Discard generated audio after the current chunk and re-generate."""
        with self._lock:
            current_idx = 0
            for i, start in enumerate(self._chunk_starts):
                if start <= self._play_pos:
                    current_idx = i
                else:
                    break
            keep = current_idx + 1

            if keep < len(self._chunk_starts):
                trunc_at = self._chunk_starts[keep]
                self._buffer = self._buffer[:trunc_at]
                self._chunk_starts = self._chunk_starts[:keep]
                self._chunks_received = keep
                self._gen_cursor = keep
                self._generation_done = False

            self._gen_epoch += 1

        self._gen_wakeup.set()

    # -- queries ------------------------------------------------------------

    @property
    def playback_time(self) -> float:
        return self._play_pos / self.sample_rate

    @property
    def buffered_duration(self) -> float:
        return len(self._buffer) / self.sample_rate

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_stopped(self) -> bool:
        return self._stopped

    @property
    def is_finished(self) -> bool:
        return self._generation_done and self._play_pos >= len(self._buffer)

    @property
    def chunks_received(self) -> int:
        return self._chunks_received

    @property
    def expected_chunks(self) -> int:
        return self._expected_chunks

    @property
    def generation_done(self) -> bool:
        return self._generation_done

    @property
    def current_chunk_index(self) -> int:
        """0-based index of the chunk currently playing."""
        with self._lock:
            idx = 0
            for i, start in enumerate(self._chunk_starts):
                if start <= self._play_pos:
                    idx = i
                else:
                    break
            return idx

    @property
    def total_chunks(self) -> int:
        return len(self._chunk_starts)

    # -- sounddevice callback -----------------------------------------------

    def _callback(
        self,
        outdata: np.ndarray,
        frames: int,
        _time_info: object,
        _status: sd.CallbackFlags,
    ) -> None:
        if self._paused or self._stopped:
            outdata[:] = 0
            return

        with self._lock:
            available = len(self._buffer)
            if self._play_pos >= available:
                outdata[:] = 0
                return

            to_read = min(frames, available - self._play_pos)
            outdata[:to_read, 0] = self._buffer[self._play_pos : self._play_pos + to_read]
            if to_read < frames:
                outdata[to_read:] = 0
            self._play_pos += to_read
