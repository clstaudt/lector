"""Tests for lector.utils — clipboard and stdin helpers.

Property-based: ``read_stdin`` always returns stripped text for any input.
Contract-based: ``deal.cases`` auto-tests the ``@deal.post`` on both
functions (result is always stripped).
Example-based: platform dispatch (one per OS) and the "no tool" error
are inherently discrete cases best checked by example.
"""

from __future__ import annotations

import subprocess
from io import StringIO
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lector.utils import read_clipboard, read_stdin

# ---------------------------------------------------------------------------
# Property: read_stdin strips any text
# ---------------------------------------------------------------------------


@given(text=st.text())
def test_read_stdin_strips_any_text(text: str) -> None:
    """For arbitrary text, read_stdin must return the stripped version."""
    with patch("lector.utils.sys.stdin", new=StringIO(text)):
        assert read_stdin() == text.strip()


# ---------------------------------------------------------------------------
# read_clipboard — platform dispatch (example-based, one per OS path)
# ---------------------------------------------------------------------------

_PLATFORM_CASES: list[tuple[str, dict, list[str]]] = [
    ("Darwin", {}, ["pbpaste"]),
    ("Windows", {}, ["powershell", "-NoProfile", "-Command", "Get-Clipboard"]),
]


class TestReadClipboardDispatch:
    """Each platform dispatches to the correct clipboard command."""

    @pytest.mark.parametrize(("os_name", "which_map", "expected_cmd"), _PLATFORM_CASES)
    def test_platform_command(
        self,
        os_name: str,
        which_map: dict,
        expected_cmd: list[str],
    ) -> None:
        def _which(cmd: str) -> str | None:
            return which_map.get(cmd)

        with (
            patch("lector.utils.platform.system", return_value=os_name),
            patch("lector.utils.shutil.which", side_effect=_which),
            patch("lector.utils.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=expected_cmd, returncode=0, stdout="text"
            )
            read_clipboard()

        assert mock_run.call_args[0][0] == expected_cmd

    def test_linux_prefers_wl_paste_over_xclip(self) -> None:
        """When both wl-paste and xclip exist, wl-paste wins."""

        def _which(cmd: str) -> str | None:
            return {
                "wl-paste": "/usr/bin/wl-paste",
                "xclip": "/usr/bin/xclip",
            }.get(cmd)

        with (
            patch("lector.utils.platform.system", return_value="Linux"),
            patch("lector.utils.shutil.which", side_effect=_which),
            patch("lector.utils.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="wayland text"
            )
            read_clipboard()

        assert mock_run.call_args[0][0] == ["wl-paste", "--no-newline"]

    @pytest.mark.parametrize(
        ("which_map", "expected_cmd"),
        [
            ({"xclip": "/usr/bin/xclip"}, ["xclip", "-selection", "clipboard", "-o"]),
            ({"xsel": "/usr/bin/xsel"}, ["xsel", "--clipboard", "--output"]),
        ],
    )
    def test_linux_fallback_tools(self, which_map: dict, expected_cmd: list[str]) -> None:
        """Linux falls back through xclip → xsel when wl-paste is absent."""

        def _which(cmd: str) -> str | None:
            return which_map.get(cmd)

        with (
            patch("lector.utils.platform.system", return_value="Linux"),
            patch("lector.utils.shutil.which", side_effect=_which),
            patch("lector.utils.subprocess.run") as mock_run,
        ):
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="text"
            )
            read_clipboard()

        assert mock_run.call_args[0][0] == expected_cmd


# ---------------------------------------------------------------------------
# read_clipboard — error cases (example-based)
# ---------------------------------------------------------------------------


class TestReadClipboardErrors:
    """Error paths are discrete cases, best tested by example."""

    def test_linux_no_tool_raises(self) -> None:
        with (
            patch("lector.utils.platform.system", return_value="Linux"),
            patch("lector.utils.shutil.which", return_value=None),
            pytest.raises(RuntimeError, match="No clipboard tool found"),
        ):
            read_clipboard()

    def test_unsupported_platform_raises(self) -> None:
        with (
            patch("lector.utils.platform.system", return_value="Haiku"),
            pytest.raises(RuntimeError, match="not supported"),
        ):
            read_clipboard()


# ---------------------------------------------------------------------------
# Property: read_clipboard always strips whitespace
# ---------------------------------------------------------------------------


@given(padding=st.text(alphabet=" \t\n\r", min_size=0, max_size=10))
def test_clipboard_always_strips(padding: str) -> None:
    """Regardless of surrounding whitespace, the result is stripped."""
    raw = f"{padding}core text{padding}"
    with (
        patch("lector.utils.platform.system", return_value="Darwin"),
        patch("lector.utils.subprocess.run") as mock_run,
    ):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pbpaste"], returncode=0, stdout=raw
        )
        result = read_clipboard()

    assert result == raw.strip()
