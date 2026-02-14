"""Tests for lector.tts — model paths, download, and player factory.

Only network I/O (``urllib.request.urlretrieve``) is mocked.
Path logic and constants are tested against real values.
The ``create_player`` tests use the shared ``FakeKokoroEngine`` from
conftest — the real ``create_player`` logic runs end-to-end.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from lector.player import AudioPlayer
from lector.tts import MODEL_DIR, MODELS, create_player, download_models, get_model_paths

# ---------------------------------------------------------------------------
# Pure model-path logic (no mocks)
# ---------------------------------------------------------------------------


class TestModelPaths:
    def test_model_dir_under_home(self) -> None:
        assert str(MODEL_DIR).startswith(str(Path.home()))

    def test_model_dir_name(self) -> None:
        assert MODEL_DIR.name == "models"
        assert MODEL_DIR.parent.name == ".lector"

    def test_get_model_paths_returns_expected_names(self) -> None:
        model, voices = get_model_paths()
        assert model.name == "kokoro-v1.0.onnx"
        assert voices.name == "voices-v1.0.bin"

    def test_get_model_paths_share_parent(self) -> None:
        model, voices = get_model_paths()
        assert model.parent == voices.parent == MODEL_DIR

    def test_models_dict_has_expected_keys(self) -> None:
        assert "kokoro-v1.0.onnx" in MODELS
        assert "voices-v1.0.bin" in MODELS

    def test_model_urls_are_https(self) -> None:
        for url in MODELS.values():
            assert url.startswith("https://")


# ---------------------------------------------------------------------------
# download_models — mock only the network call
# ---------------------------------------------------------------------------


class TestDownloadModels:
    def test_download_creates_files(self, tmp_path: Path) -> None:
        """download_models should write files to MODEL_DIR via urlretrieve."""

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
        """download_models should skip files that already exist."""
        for name in MODELS:
            (tmp_path / name).write_bytes(b"existing")

        with (
            patch("lector.tts.MODEL_DIR", tmp_path),
            patch("lector.tts.urllib.request.urlretrieve") as mock_retrieve,
        ):
            download_models()

        mock_retrieve.assert_not_called()

    def test_download_force_redownloads(self, tmp_path: Path) -> None:
        """download_models(force=True) should re-download even if present."""
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
# create_player — uses the fake engine from conftest
# ---------------------------------------------------------------------------


class TestCreatePlayer:
    """Let create_player run its real logic with a fake engine."""

    def test_returns_audio_player(self, fake_engine) -> None:
        with patch("lector.tts.get_engine", return_value=fake_engine):
            player = create_player("Hello. How are you?")

        assert isinstance(player, AudioPlayer)

    def test_player_has_correct_metadata(self, fake_engine) -> None:
        with patch("lector.tts.get_engine", return_value=fake_engine):
            player = create_player("Test text.", voice="af_nicole", speed=1.5, lang="en-gb")

        assert player.voice == "af_nicole"
        assert player.speed == 1.5
        assert player.lang == "en-gb"

    def test_player_has_phoneme_batches(self, fake_engine) -> None:
        with patch("lector.tts.get_engine", return_value=fake_engine):
            player = create_player("First sentence. Second sentence.")

        assert player.expected_chunks >= 2

    def test_player_sample_rate(self, fake_engine) -> None:
        with patch("lector.tts.get_engine", return_value=fake_engine):
            player = create_player("Hello.")

        assert player.sample_rate == 24_000
