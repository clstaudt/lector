"""Tests for lector.utils — clipboard and stdin helpers.

Only ``subprocess.run`` (the actual OS call) is mocked for clipboard
tests.  All platform-dispatch logic runs for real.
"""

from __future__ import annotations

import subprocess
from io import StringIO
from unittest.mock import patch

import pytest

from lector.utils import read_clipboard, read_stdin


# ---------------------------------------------------------------------------
# read_clipboard
# ---------------------------------------------------------------------------


class TestReadClipboard:
    """read_clipboard dispatches to the right OS tool."""

    def test_macos_uses_pbpaste(self) -> None:
        with (
            patch("lector.utils.platform.system", return_value="Darwin"),
            patch("lector.utils.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=["pbpaste"], returncode=0, stdout="hello from clipboard\n"
            )
            result = read_clipboard()

        assert result == "hello from clipboard"
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["pbpaste"]

    def test_linux_prefers_wl_paste(self) -> None:
        with (
            patch("lector.utils.platform.system", return_value="Linux"),
            patch("lector.utils.shutil.which", side_effect=lambda cmd: "/usr/bin/wl-paste" if cmd == "wl-paste" else None),
            patch("lector.utils.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="wayland text"
            )
            result = read_clipboard()

        assert result == "wayland text"
        assert mock_run.call_args[0][0] == ["wl-paste", "--no-newline"]

    def test_linux_falls_back_to_xclip(self) -> None:
        def which_side_effect(cmd: str) -> str | None:
            if cmd == "xclip":
                return "/usr/bin/xclip"
            return None

        with (
            patch("lector.utils.platform.system", return_value="Linux"),
            patch("lector.utils.shutil.which", side_effect=which_side_effect),
            patch("lector.utils.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="xclip text"
            )
            result = read_clipboard()

        assert result == "xclip text"
        assert mock_run.call_args[0][0] == ["xclip", "-selection", "clipboard", "-o"]

    def test_linux_falls_back_to_xsel(self) -> None:
        def which_side_effect(cmd: str) -> str | None:
            if cmd == "xsel":
                return "/usr/bin/xsel"
            return None

        with (
            patch("lector.utils.platform.system", return_value="Linux"),
            patch("lector.utils.shutil.which", side_effect=which_side_effect),
            patch("lector.utils.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="xsel text"
            )
            result = read_clipboard()

        assert result == "xsel text"
        assert mock_run.call_args[0][0] == ["xsel", "--clipboard", "--output"]

    def test_linux_no_tool_raises(self) -> None:
        with (
            patch("lector.utils.platform.system", return_value="Linux"),
            patch("lector.utils.shutil.which", return_value=None),
        ):
            with pytest.raises(RuntimeError, match="No clipboard tool found"):
                read_clipboard()

    def test_windows_uses_powershell(self) -> None:
        with (
            patch("lector.utils.platform.system", return_value="Windows"),
            patch("lector.utils.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="windows text\r\n"
            )
            result = read_clipboard()

        assert result == "windows text"
        cmd = mock_run.call_args[0][0]
        assert "powershell" in cmd[0].lower() or cmd[0] == "powershell"

    def test_unsupported_platform_raises(self) -> None:
        with patch("lector.utils.platform.system", return_value="Haiku"):
            with pytest.raises(RuntimeError, match="not supported"):
                read_clipboard()

    def test_strips_whitespace(self) -> None:
        with (
            patch("lector.utils.platform.system", return_value="Darwin"),
            patch("lector.utils.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="  padded text  \n"
            )
            assert read_clipboard() == "padded text"


# ---------------------------------------------------------------------------
# read_stdin
# ---------------------------------------------------------------------------


class TestReadStdin:
    def test_reads_and_strips(self) -> None:
        with patch("lector.utils.sys.stdin", new=StringIO("  hello from pipe  \n")):
            assert read_stdin() == "hello from pipe"

    def test_empty_stdin(self) -> None:
        with patch("lector.utils.sys.stdin", new=StringIO("")):
            assert read_stdin() == ""

    def test_multiline(self) -> None:
        text = "line one\nline two\nline three\n"
        with patch("lector.utils.sys.stdin", new=StringIO(text)):
            result = read_stdin()
        assert "line one" in result
        assert "line three" in result
