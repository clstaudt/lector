"""Tests for lector (unit-level, no model files required)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from lector.tts import MODEL_DIR, get_model_paths
from lector.utils import install_macos_quick_action, read_clipboard, read_stdin


def test_read_clipboard():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="Hello world\n")
        assert read_clipboard() == "Hello world"


def test_read_stdin():
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = "  Hello from stdin  "
        assert read_stdin() == "Hello from stdin"


def test_get_model_paths():
    model, voices = get_model_paths()
    assert model.name == "kokoro-v1.0.onnx"
    assert voices.name == "voices-v1.0.bin"
    assert model.parent == voices.parent


def test_model_dir_is_under_home():
    assert str(MODEL_DIR).startswith(str(Path.home()))


def test_install_macos_quick_action(tmp_path: Path):
    """Verify the Quick Action plist is written correctly."""
    with (
        patch("lector.utils.Path.home", return_value=tmp_path),
        patch("shutil.which", return_value="/usr/local/bin/lector"),
    ):
        bundle = install_macos_quick_action()
        wflow = bundle / "Contents" / "document.wflow"
        assert wflow.exists()
        content = wflow.read_text()
        assert "lector" in content
        assert "com.apple.Automator.servicesMenu" in content
