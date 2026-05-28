"""Tests for lector.tts — model paths, download, and player factory.

Contract-based: ``deal.cases`` auto-tests the ``@deal.post`` contracts on
``get_model_paths`` (same parent, correct suffixes).
Property-based: ``create_player`` properties checked with hypothesis —
metadata passes through, chunk count scales with sentences.
Example-based: download logic (mocked network I/O) and model URL format
are discrete checks best kept as examples.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import deal
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lector.player import AudioPlayer
from lector.tts import MODELS, create_player, download_models, get_model_paths

from .conftest import FakeKokoroEngine

# ---------------------------------------------------------------------------
# Contract-driven tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", deal.cases(get_model_paths))
def test_get_model_paths_contracts(case: deal.TestCase) -> None:
    """Verify get_model_paths postconditions: same parent, correct suffixes."""
    case()


# ---------------------------------------------------------------------------
# Properties: model path invariants
# ---------------------------------------------------------------------------


def test_model_paths_under_home() -> None:
    """Both model paths must live under the user's home directory."""
    model, voices = get_model_paths()
    home = str(Path.home())
    assert str(model).startswith(home)
    assert str(voices).startswith(home)


def test_model_urls_are_https() -> None:
    """Every model download URL must use HTTPS."""
    for url in MODELS.values():
        assert url.startswith("https://")


# ---------------------------------------------------------------------------
# download_models — example-based (mocked network I/O)
# ---------------------------------------------------------------------------


class TestDownloadModels:
    """Download logic uses the real code path with mocked urlretrieve."""

    def test_download_creates_both_files(self, tmp_path: Path) -> None:
        def fake_urlretrieve(url: str, dest: str | Path, reporthook=None) -> None:
            Path(dest).write_bytes(b"fake model data")

        with (
            patch("lector.tts.MODEL_DIR", tmp_path),
            patch("lector.tts.urllib.request.urlretrieve", side_effect=fake_urlretrieve),
        ):
            download_models()

        assert (tmp_path / "kokoro-v1.0.onnx").exists()
        assert (tmp_path / "voices-v1.0.bin").exists()

    def test_download_skips_existing(self, tmp_path: Path) -> None:
        for name in MODELS:
            (tmp_path / name).write_bytes(b"existing")

        with (
            patch("lector.tts.MODEL_DIR", tmp_path),
            patch("lector.tts.urllib.request.urlretrieve") as mock_retrieve,
        ):
            download_models()

        mock_retrieve.assert_not_called()

    def test_download_force_redownloads(self, tmp_path: Path) -> None:
        for name in MODELS:
            (tmp_path / name).write_bytes(b"old")

        def fake_urlretrieve(url: str, dest: str | Path, reporthook=None) -> None:
            Path(dest).write_bytes(b"new model data")

        with (
            patch("lector.tts.MODEL_DIR", tmp_path),
            patch("lector.tts.urllib.request.urlretrieve", side_effect=fake_urlretrieve),
        ):
            download_models(force=True)

        assert (tmp_path / "kokoro-v1.0.onnx").read_bytes() == b"new model data"


# ---------------------------------------------------------------------------
# Properties: create_player metadata pass-through
# ---------------------------------------------------------------------------


_VOICE_STRATEGY = st.sampled_from(["af_sky", "af_nicole", "am_adam"])
_SPEED_STRATEGY = st.floats(min_value=0.5, max_value=2.0)
_LANG_STRATEGY = st.sampled_from(["en-us", "en-gb", "fr-fr", "de-de"])


@given(voice=_VOICE_STRATEGY, speed=_SPEED_STRATEGY, lang=_LANG_STRATEGY)
@settings(max_examples=30)
def test_create_player_preserves_metadata(voice: str, speed: float, lang: str) -> None:
    """Voice, speed, and lang always pass through to the player unchanged."""
    engine = FakeKokoroEngine()
    with patch("lector.tts.get_engine", return_value=engine):
        player = create_player("Hello, world.", voice=voice, speed=speed, lang=lang)

    assert player.voice == voice
    assert player.speed == speed
    assert player.lang == lang


def test_create_player_returns_audio_player() -> None:
    """create_player must return an AudioPlayer instance."""
    engine = FakeKokoroEngine()
    with patch("lector.tts.get_engine", return_value=engine):
        player = create_player("Hello.")
    assert isinstance(player, AudioPlayer)


def test_create_player_sample_rate() -> None:
    """Player sample rate must be 24000 Hz."""
    engine = FakeKokoroEngine()
    with patch("lector.tts.get_engine", return_value=engine):
        player = create_player("Hello.")
    assert player.sample_rate == 24_000


def test_create_player_chunk_count_scales_with_sentences() -> None:
    """More sentences should produce at least as many chunks."""
    engine = FakeKokoroEngine()
    with patch("lector.tts.get_engine", return_value=engine):
        short = create_player("One.")
        long = create_player("One. Two. Three. Four. Five.")
    assert long.expected_chunks >= short.expected_chunks
