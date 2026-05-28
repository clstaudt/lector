"""Helpers — clipboard access and stdin reading."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys

import deal

# ---------------------------------------------------------------------------
# Text input helpers
# ---------------------------------------------------------------------------


@deal.post(lambda result: result == result.strip())
def read_clipboard() -> str:
    """Read text from the system clipboard.

    Supported platforms:
    - **macOS** — ``pbpaste``
    - **Linux / BSD** — ``xclip`` or ``xsel`` (X11), ``wl-paste`` (Wayland)
    - **Windows** — ``powershell Get-Clipboard``

    Raises:
    ------
    RuntimeError
        If no supported clipboard tool is found.
    """
    system = platform.system()

    if system == "Darwin":
        cmd = ["pbpaste"]
    elif system == "Linux" or system.endswith("BSD"):
        if shutil.which("wl-paste"):
            cmd = ["wl-paste", "--no-newline"]
        elif shutil.which("xclip"):
            cmd = ["xclip", "-selection", "clipboard", "-o"]
        elif shutil.which("xsel"):
            cmd = ["xsel", "--clipboard", "--output"]
        else:
            raise RuntimeError("No clipboard tool found. Install xclip, xsel, or wl-paste.")
    elif system == "Windows":
        cmd = ["powershell", "-NoProfile", "-Command", "Get-Clipboard"]
    else:
        raise RuntimeError(f"Clipboard reading is not supported on {system}.")

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


@deal.post(lambda result: result == result.strip())
def read_stdin() -> str:
    """Read all text from stdin."""
    return sys.stdin.read().strip()
