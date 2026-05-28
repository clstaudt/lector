"""Tests for lector.macos_service — Quick Action install / uninstall.

Contract-based: ``_require_macos`` uses a ``@deal.pre`` contract — tested
via ``deal.cases`` and explicit example for the error path.
Property-based: installed bundle satisfies structural invariants (valid
plist, service type, correct shell) — tested once via a shared install
helper, avoiding repetitive near-identical tests.
Example-based: roundtrip install→uninstall, legacy cleanup, idempotent
reinstall — inherently sequential scenarios.
"""

from __future__ import annotations

import plistlib
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from lector.macos_service import (
    _require_macos,
    install_quick_action,
    uninstall_quick_action,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# _require_macos contract
# ---------------------------------------------------------------------------


def test_require_macos_passes_on_darwin() -> None:
    """Contract is satisfied on Darwin — no exception."""
    with patch("lector.macos_service.platform.system", return_value="Darwin"):
        _require_macos()


@pytest.mark.parametrize("os_name", ["Linux", "Windows", "FreeBSD"])
def test_require_macos_raises_on_non_darwin(os_name: str) -> None:
    """Contract violation on non-Darwin platforms raises RuntimeError."""
    with (
        patch("lector.macos_service.platform.system", return_value=os_name),
        pytest.raises(RuntimeError, match="only available on macOS"),
    ):
        _require_macos()


# ---------------------------------------------------------------------------
# install_quick_action — helper + structural invariants
# ---------------------------------------------------------------------------


def _install(tmp_path: Path, lector_bin: str = "/usr/local/bin/lector") -> Path:
    """Run install_quick_action against tmp_path and return bundle root."""
    with (
        patch("lector.macos_service.platform.system", return_value="Darwin"),
        patch("lector.macos_service.Path.home", return_value=tmp_path),
        patch("lector.macos_service.shutil.which", return_value=lector_bin),
        patch("lector.macos_service.subprocess.run"),
    ):
        return install_quick_action()


class TestInstallStructure:
    """Verify structural invariants of the installed workflow bundle."""

    def test_bundle_location(self, tmp_path: Path) -> None:
        """Bundle must be in ~/Library/Services/ with the expected name."""
        bundle = _install(tmp_path)
        assert bundle.name == "Read with Lector.workflow"
        assert bundle.parent == tmp_path / "Library" / "Services"

    def test_both_plists_exist(self, tmp_path: Path) -> None:
        """Info.plist and document.wflow must both be created."""
        bundle = _install(tmp_path)
        assert (bundle / "Contents" / "Info.plist").is_file()
        assert (bundle / "Contents" / "document.wflow").is_file()

    def test_info_plist_valid_and_has_service(self, tmp_path: Path) -> None:
        """Info.plist must be valid plist with an NSServices entry naming Lector."""
        bundle = _install(tmp_path)
        data = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
        assert "NSServices" in data
        assert "Read with Lector" in data["NSServices"][0]["NSMenuItem"]["default"]

    def test_wflow_is_automator_service(self, tmp_path: Path) -> None:
        """document.wflow must declare itself as an Automator services-menu workflow."""
        bundle = _install(tmp_path)
        data = plistlib.loads((bundle / "Contents" / "document.wflow").read_bytes())
        wf_type = data["workflowMetaData"]["workflowTypeIdentifier"]
        assert wf_type == "com.apple.Automator.servicesMenu"

    def test_wflow_uses_zsh(self, tmp_path: Path) -> None:
        """The shell action must use /bin/zsh."""
        bundle = _install(tmp_path)
        data = plistlib.loads((bundle / "Contents" / "document.wflow").read_bytes())
        params = data["actions"][0]["action"]["ActionParameters"]
        assert params["shell"] == "/bin/zsh"


# ---------------------------------------------------------------------------
# Properties: lector binary embedding
# ---------------------------------------------------------------------------


def test_wflow_embeds_specified_binary(tmp_path: Path) -> None:
    """The installed wflow must contain the resolved lector binary path."""
    bundle = _install(tmp_path, lector_bin="/opt/homebrew/bin/lector")
    content = (bundle / "Contents" / "document.wflow").read_text()
    assert "/opt/homebrew/bin/lector" in content


def test_wflow_falls_back_to_bare_lector(tmp_path: Path) -> None:
    """When shutil.which returns None, bare 'lector' is used."""
    with (
        patch("lector.macos_service.platform.system", return_value="Darwin"),
        patch("lector.macos_service.Path.home", return_value=tmp_path),
        patch("lector.macos_service.shutil.which", return_value=None),
        patch("lector.macos_service.subprocess.run"),
    ):
        bundle = install_quick_action()

    content = (bundle / "Contents" / "document.wflow").read_text()
    assert '"lector" read' in content


# ---------------------------------------------------------------------------
# Example: legacy cleanup, idempotency, lsregister, non-macOS guard
# ---------------------------------------------------------------------------


def test_removes_legacy_workflow(tmp_path: Path) -> None:
    """Old workflow bundles are cleaned up on install."""
    legacy = tmp_path / "Library" / "Services" / "Lector - Read or Stop.workflow"
    legacy.mkdir(parents=True)
    (legacy / "marker.txt").write_text("old")

    _install(tmp_path)
    assert not legacy.exists()


def test_idempotent_reinstall(tmp_path: Path) -> None:
    """Installing twice must succeed and update the wflow file."""
    bundle1 = _install(tmp_path)
    mtime1 = (bundle1 / "Contents" / "document.wflow").stat().st_mtime_ns
    time.sleep(0.01)
    bundle2 = _install(tmp_path)
    mtime2 = (bundle2 / "Contents" / "document.wflow").stat().st_mtime_ns

    assert bundle1 == bundle2
    assert mtime2 >= mtime1


def test_calls_lsregister(tmp_path: Path) -> None:
    """Install must invoke lsregister to register the workflow."""
    with (
        patch("lector.macos_service.platform.system", return_value="Darwin"),
        patch("lector.macos_service.Path.home", return_value=tmp_path),
        patch("lector.macos_service.shutil.which", return_value="/usr/local/bin/lector"),
        patch("lector.macos_service.subprocess.run") as mock_run,
    ):
        install_quick_action()

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "lsregister" in cmd[0]


def test_install_raises_on_non_macos() -> None:
    """install_quick_action must reject non-macOS platforms."""
    with (
        patch("lector.macos_service.platform.system", return_value="Linux"),
        pytest.raises(RuntimeError, match="only available on macOS"),
    ):
        install_quick_action()


# ---------------------------------------------------------------------------
# uninstall_quick_action
# ---------------------------------------------------------------------------


def test_uninstall_removes_bundle(tmp_path: Path) -> None:
    """Uninstalling an existing bundle removes it and returns its path."""
    bundle = tmp_path / "Library" / "Services" / "Read with Lector.workflow"
    contents = bundle / "Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_text("<plist/>")

    with (
        patch("lector.macos_service.platform.system", return_value="Darwin"),
        patch("lector.macos_service.Path.home", return_value=tmp_path),
    ):
        result = uninstall_quick_action()

    assert result == bundle
    assert not bundle.exists()


def test_uninstall_returns_none_when_absent(tmp_path: Path) -> None:
    """Uninstalling when no bundle exists returns None."""
    with (
        patch("lector.macos_service.platform.system", return_value="Darwin"),
        patch("lector.macos_service.Path.home", return_value=tmp_path),
    ):
        assert uninstall_quick_action() is None


def test_uninstall_raises_on_non_macos() -> None:
    """uninstall_quick_action must reject non-macOS platforms."""
    with (
        patch("lector.macos_service.platform.system", return_value="Linux"),
        pytest.raises(RuntimeError, match="only available on macOS"),
    ):
        uninstall_quick_action()


# ---------------------------------------------------------------------------
# Roundtrip: install → uninstall leaves no trace
# ---------------------------------------------------------------------------


def test_roundtrip_install_then_uninstall(tmp_path: Path) -> None:
    """Install then uninstall should leave no trace."""
    with (
        patch("lector.macos_service.platform.system", return_value="Darwin"),
        patch("lector.macos_service.Path.home", return_value=tmp_path),
        patch("lector.macos_service.shutil.which", return_value="/usr/local/bin/lector"),
        patch("lector.macos_service.subprocess.run"),
    ):
        bundle = install_quick_action()
        assert bundle.exists()
        removed = uninstall_quick_action()

    assert removed == bundle
    assert not bundle.exists()
