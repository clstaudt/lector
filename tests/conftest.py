"""Shared test fixtures.

The only "big" fake in the suite is ``FakeKokoroEngine`` — a lightweight
stand-in for the real ``Kokoro`` ONNX engine that would otherwise need
~300 MB of model files.  Everything else (AudioPlayer, CLI parsing,
plist generation, …) runs as real code.
"""

from __future__ import annotations

import re
import time

import numpy as np
import pytest

from lector.player import AudioPlayer

# ---------------------------------------------------------------------------
# Lightweight Kokoro engine stand-in
# ---------------------------------------------------------------------------


class _FakeTokenizer:
    """Mimic ``kokoro_onnx.Kokoro.tokenizer``."""

    def phonemize(self, text: str, lang: str) -> str:
        """Return the text itself as 'phonemes' — good enough for testing."""
        return text


class FakeKokoroEngine:
    """Drop-in replacement for ``kokoro_onnx.Kokoro``.

    * ``tokenizer.phonemize`` → returns the text unchanged.
    * ``_split_phonemes``     → splits on sentence-ending punctuation.
    * ``get_voice_style``     → returns a small zero array.
    * ``_create_audio``       → returns a short sine-wave chunk.
    * ``get_voices``          → returns a fixed voice list.
    """

    SAMPLE_RATE = 24_000

    def __init__(self) -> None:
        self.tokenizer = _FakeTokenizer()

    # -- voice catalogue ---------------------------------------------------

    @staticmethod
    def get_voices() -> list[str]:
        """Return a fixed set of test voices."""
        return ["af_sky", "af_nicole", "am_adam"]

    @staticmethod
    def get_voice_style(voice: str) -> np.ndarray:
        """Return a dummy voice style vector."""
        return np.zeros(256, dtype=np.float32)

    # -- phoneme splitting -------------------------------------------------

    @staticmethod
    def _split_phonemes(phonemes: str) -> list[str]:
        """Naïve split: one chunk per sentence (period / newline)."""
        chunks = [c.strip() for c in re.split(r"[.\n]+", phonemes) if c.strip()]
        return chunks or [phonemes]

    # -- audio generation --------------------------------------------------

    def _create_audio(
        self,
        phonemes: str,
        voice_style: np.ndarray,
        speed: float,
    ) -> tuple[np.ndarray, float]:
        """Return a 0.25-second sine-wave chunk (mono, float32)."""
        duration = 0.25
        n_samples = int(self.SAMPLE_RATE * duration)
        t = np.linspace(0, duration, n_samples, dtype=np.float32)
        audio = 0.3 * np.sin(2 * np.pi * 440 * t)
        return audio, self.SAMPLE_RATE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_engine() -> FakeKokoroEngine:
    """Provide a ready-to-use fake TTS engine (no model files needed)."""
    return FakeKokoroEngine()


def make_player(
    fake_engine: FakeKokoroEngine, text: str = "First. Second. Third.", **kw
) -> AudioPlayer:
    """Build a real AudioPlayer wired to the fake engine."""
    phonemes = fake_engine.tokenizer.phonemize(text, "en-us")
    batches = fake_engine._split_phonemes(phonemes)
    style = fake_engine.get_voice_style("af_sky")
    defaults = {
        "sample_rate": 24_000,
        "voice": "af_sky",
        "speed": 1.0,
        "lang": "en-us",
        "engine": fake_engine,
        "voice_style": style,
        "phoneme_batches": batches,
    }
    defaults.update(kw)
    return AudioPlayer(**defaults)


def generate_fully(player: AudioPlayer, timeout: float = 5.0) -> None:
    """Start generation and block until complete (or timeout)."""
    player.start_generation()
    deadline = time.monotonic() + timeout
    while not player.generation_done and time.monotonic() < deadline:
        time.sleep(0.05)
