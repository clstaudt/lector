"""Tests for lector.macos_service — Quick Action install / uninstall.

Real filesystem operations run against ``tmp_path``.
Only ``subprocess.run`` (lsregister) and ``platform.system`` are mocked.
The generated plist files are parsed back with ``plistlib`` to verify
structure rather than doing fragile string matching.
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
# Platform guard
# ---------------------------------------------------------------------------


class TestRequireMacOS:
    def test_passes_on_darwin(self) -> None:
        with patch("lector.macos_service.platform.system", return_value="Darwin"):
            _require_macos()  # should not raise

    @pytest.mark.parametrize("os_name", ["Linux", "Windows", "FreeBSD"])
    def test_raises_on_non_darwin(self, os_name: str) -> None:
        with (
            patch("lector.macos_service.platform.system", return_value=os_name),
            pytest.raises(RuntimeError, match="only available on macOS"),
        ):
            _require_macos()


# ---------------------------------------------------------------------------
# install_quick_action — real FS in tmp_path
# ---------------------------------------------------------------------------


class TestInstallQuickAction:
    """All filesystem writes happen for real inside tmp_path."""

    def _install(self, tmp_path: Path, lector_bin: str = "/usr/local/bin/lector") -> Path:
        """Run install_quick_action against tmp_path and return bundle root."""
        with (
            patch("lector.macos_service.platform.system", return_value="Darwin"),
            patch("lector.macos_service.Path.home", return_value=tmp_path),
            patch("lector.macos_service.shutil.which", return_value=lector_bin),
            patch("lector.macos_service.subprocess.run"),  # suppress lsregister
        ):
            return install_quick_action()

    def test_returns_workflow_bundle_path(self, tmp_path: Path) -> None:
        bundle = self._install(tmp_path)
        assert bundle.name == "Read with Lector.workflow"
        assert bundle.parent == tmp_path / "Library" / "Services"

    def test_creates_info_plist(self, tmp_path: Path) -> None:
        bundle = self._install(tmp_path)
        info_path = bundle / "Contents" / "Info.plist"
        assert info_path.is_file()

    def test_info_plist_is_valid_plist(self, tmp_path: Path) -> None:
        bundle = self._install(tmp_path)
        info_path = bundle / "Contents" / "Info.plist"
        data = plistlib.loads(info_path.read_bytes())
        assert "NSServices" in data

    def test_info_plist_has_service_name(self, tmp_path: Path) -> None:
        bundle = self._install(tmp_path)
        info_path = bundle / "Contents" / "Info.plist"
        data = plistlib.loads(info_path.read_bytes())
        service = data["NSServices"][0]
        assert "Read with Lector" in service["NSMenuItem"]["default"]

    def test_creates_document_wflow(self, tmp_path: Path) -> None:
        bundle = self._install(tmp_path)
        wflow_path = bundle / "Contents" / "document.wflow"
        assert wflow_path.is_file()

    def test_wflow_is_valid_plist(self, tmp_path: Path) -> None:
        bundle = self._install(tmp_path)
        wflow_path = bundle / "Contents" / "document.wflow"
        data = plistlib.loads(wflow_path.read_bytes())
        assert "actions" in data

    def test_wflow_contains_lector_command(self, tmp_path: Path) -> None:
        bundle = self._install(tmp_path)
        wflow_path = bundle / "Contents" / "document.wflow"
        content = wflow_path.read_text()
        assert "lector" in content

    def test_wflow_embeds_correct_binary_path(self, tmp_path: Path) -> None:
        bundle = self._install(tmp_path, lector_bin="/opt/homebrew/bin/lector")
        wflow_path = bundle / "Contents" / "document.wflow"
        content = wflow_path.read_text()
        assert "/opt/homebrew/bin/lector" in content

    def test_wflow_falls_back_to_bare_lector(self, tmp_path: Path) -> None:
        """When shutil.which returns None, use bare 'lector'."""
        with (
            patch("lector.macos_service.platform.system", return_value="Darwin"),
            patch("lector.macos_service.Path.home", return_value=tmp_path),
            patch("lector.macos_service.shutil.which", return_value=None),
            patch("lector.macos_service.subprocess.run"),
        ):
            bundle = install_quick_action()

        wflow_path = bundle / "Contents" / "document.wflow"
        content = wflow_path.read_text()
        assert '"lector" read' in content

    def test_wflow_is_automator_service_type(self, tmp_path: Path) -> None:
        bundle = self._install(tmp_path)
        wflow_path = bundle / "Contents" / "document.wflow"
        data = plistlib.loads(wflow_path.read_bytes())
        type_id = data["workflowMetaData"]["workflowTypeIdentifier"]
        assert type_id == "com.apple.Automator.servicesMenu"

    def test_wflow_uses_zsh_shell(self, tmp_path: Path) -> None:
        bundle = self._install(tmp_path)
        wflow_path = bundle / "Contents" / "document.wflow"
        data = plistlib.loads(wflow_path.read_bytes())
        action_params = data["actions"][0]["action"]["ActionParameters"]
        assert action_params["shell"] == "/bin/zsh"

    def test_removes_legacy_workflow(self, tmp_path: Path) -> None:
        legacy = tmp_path / "Library" / "Services" / "Lector - Read or Stop.workflow"
        legacy.mkdir(parents=True)
        (legacy / "marker.txt").write_text("old")

        self._install(tmp_path)
        assert not legacy.exists()

    def test_idempotent_reinstall(self, tmp_path: Path) -> None:
        """Installing twice should succeed and update files."""
        bundle1 = self._install(tmp_path)
        mtime1 = (bundle1 / "Contents" / "document.wflow").stat().st_mtime_ns

        time.sleep(0.01)  # ensure different mtime

        bundle2 = self._install(tmp_path)
        mtime2 = (bundle2 / "Contents" / "document.wflow").stat().st_mtime_ns

        assert bundle1 == bundle2
        assert mtime2 >= mtime1

    def test_calls_lsregister(self, tmp_path: Path) -> None:
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

    def test_raises_on_non_macos(self) -> None:
        with (
            patch("lector.macos_service.platform.system", return_value="Linux"),
            pytest.raises(RuntimeError, match="only available on macOS"),
        ):
            install_quick_action()


# ---------------------------------------------------------------------------
# uninstall_quick_action — real FS in tmp_path
# ---------------------------------------------------------------------------


class TestUninstallQuickAction:
    def test_removes_existing_bundle(self, tmp_path: Path) -> None:
        bundle = tmp_path / "Library" / "Services" / "Read with Lector.workflow"
        contents = bundle / "Contents"
        contents.mkdir(parents=True)
        (contents / "Info.plist").write_text("<plist/>")
        (contents / "document.wflow").write_text("<plist/>")

        with (
            patch("lector.macos_service.platform.system", return_value="Darwin"),
            patch("lector.macos_service.Path.home", return_value=tmp_path),
        ):
            result = uninstall_quick_action()

        assert result == bundle
        assert not bundle.exists()

    def test_returns_none_when_not_installed(self, tmp_path: Path) -> None:
        with (
            patch("lector.macos_service.platform.system", return_value="Darwin"),
            patch("lector.macos_service.Path.home", return_value=tmp_path),
        ):
            result = uninstall_quick_action()

        assert result is None

    def test_raises_on_non_macos(self) -> None:
        with (
            patch("lector.macos_service.platform.system", return_value="Linux"),
            pytest.raises(RuntimeError, match="only available on macOS"),
        ):
            uninstall_quick_action()

    def test_roundtrip_install_then_uninstall(self, tmp_path: Path) -> None:
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
