"""Helpers — clipboard, stdin, macOS Quick Action installer."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


# ---------------------------------------------------------------------------
# Text input helpers
# ---------------------------------------------------------------------------

def read_clipboard() -> str:
    """Read text from the system clipboard (macOS ``pbpaste``)."""
    if sys.platform != "darwin":
        raise RuntimeError(
            "Clipboard reading via pbpaste is macOS-only. Pipe text via stdin instead."
        )
    result = subprocess.run(
        ["pbpaste"], capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def read_stdin() -> str:
    """Read all text from stdin."""
    return sys.stdin.read().strip()


# ---------------------------------------------------------------------------
# macOS Quick Action (Service) installer
# ---------------------------------------------------------------------------

_WORKFLOW_INFO_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>NSServices</key>
    <array>
        <dict>
            <key>NSMenuItem</key>
            <dict>
                <key>default</key>
                <string>Lector: Read / Stop</string>
            </dict>
            <key>NSMessage</key>
            <string>runWorkflowAsService</string>
            <key>NSSendTypes</key>
            <array>
                <string>NSStringPboardType</string>
            </array>
        </dict>
    </array>
</dict>
</plist>
"""

# Automator Quick Action plist template.
# ``{shell_command}`` is replaced at install time.
# inputMethod 0 → selected text is piped to the script's stdin.
_WORKFLOW_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>AMApplicationBuild</key>
    <string>523</string>
    <key>AMApplicationVersion</key>
    <string>2.10</string>
    <key>AMDocumentVersion</key>
    <string>2</string>
    <key>actions</key>
    <array>
        <dict>
            <key>action</key>
            <dict>
                <key>AMAccepts</key>
                <dict>
                    <key>Container</key>
                    <string>List</string>
                    <key>Optional</key>
                    <true/>
                    <key>Types</key>
                    <array>
                        <string>com.apple.cocoa.string</string>
                    </array>
                </dict>
                <key>AMActionVersion</key>
                <string>2.0.3</string>
                <key>AMApplication</key>
                <array>
                    <string>Automator</string>
                </array>
                <key>AMParameterProperties</key>
                <dict>
                    <key>COMMAND_STRING</key>
                    <dict/>
                    <key>CheckedForUserDefaultShell</key>
                    <dict/>
                    <key>inputMethod</key>
                    <dict/>
                    <key>shell</key>
                    <dict/>
                    <key>source</key>
                    <dict/>
                </dict>
                <key>AMProvides</key>
                <dict>
                    <key>Container</key>
                    <string>List</string>
                    <key>Types</key>
                    <array>
                        <string>com.apple.cocoa.string</string>
                    </array>
                </dict>
                <key>ActionBundlePath</key>
                <string>/System/Library/Automator/Run Shell Script.action</string>
                <key>ActionName</key>
                <string>Run Shell Script</string>
                <key>ActionParameters</key>
                <dict>
                    <key>COMMAND_STRING</key>
                    <string>__SHELL_COMMAND__</string>
                    <key>CheckedForUserDefaultShell</key>
                    <true/>
                    <key>inputMethod</key>
                    <integer>0</integer>
                    <key>shell</key>
                    <string>/bin/zsh</string>
                    <key>source</key>
                    <string></string>
                </dict>
                <key>BundleIdentifier</key>
                <string>com.apple.RunShellScript</string>
                <key>CFBundleVersion</key>
                <string>2.0.3</string>
                <key>CanShowSelectedItemsWhenRun</key>
                <false/>
                <key>CanShowWhenRun</key>
                <true/>
                <key>Category</key>
                <array>
                    <string>AMCategoryUtilities</string>
                </array>
                <key>Class Name</key>
                <string>RunShellScriptAction</string>
                <key>InputUUID</key>
                <string>A2BF3B5C-E1B9-4E0D-A2E5-B8A7D7E6F9C2</string>
                <key>Keywords</key>
                <array>
                    <string>Shell</string>
                    <string>Script</string>
                </array>
                <key>OutputUUID</key>
                <string>D4E5F6A7-B8C9-4D0E-A1B2-C3D4E5F6A7B8</string>
                <key>UUID</key>
                <string>F1E2D3C4-B5A6-4978-8A9B-0C1D2E3F4A5B</string>
                <key>UnlocalizedApplications</key>
                <array>
                    <string>Automator</string>
                </array>
                <key>arguments</key>
                <dict>
                    <key>0</key>
                    <dict>
                        <key>default value</key>
                        <integer>0</integer>
                        <key>name</key>
                        <string>inputMethod</string>
                        <key>required</key>
                        <string>0</string>
                        <key>type</key>
                        <string>0</string>
                        <key>uuid</key>
                        <string>0</string>
                    </dict>
                    <key>1</key>
                    <dict>
                        <key>default value</key>
                        <string></string>
                        <key>name</key>
                        <string>source</string>
                        <key>required</key>
                        <string>0</string>
                        <key>type</key>
                        <string>0</string>
                        <key>uuid</key>
                        <string>1</string>
                    </dict>
                    <key>2</key>
                    <dict>
                        <key>default value</key>
                        <false/>
                        <key>name</key>
                        <string>CheckedForUserDefaultShell</string>
                        <key>required</key>
                        <string>0</string>
                        <key>type</key>
                        <string>0</string>
                        <key>uuid</key>
                        <string>2</string>
                    </dict>
                    <key>3</key>
                    <dict>
                        <key>default value</key>
                        <string></string>
                        <key>name</key>
                        <string>COMMAND_STRING</string>
                        <key>required</key>
                        <string>0</string>
                        <key>type</key>
                        <string>0</string>
                        <key>uuid</key>
                        <string>3</string>
                    </dict>
                    <key>4</key>
                    <dict>
                        <key>default value</key>
                        <string>/bin/zsh</string>
                        <key>name</key>
                        <string>shell</string>
                        <key>required</key>
                        <string>0</string>
                        <key>type</key>
                        <string>0</string>
                        <key>uuid</key>
                        <string>4</string>
                    </dict>
                </dict>
                <key>isViewVisible</key>
                <integer>1</integer>
                <key>location</key>
                <string>529.000000:620.000000</string>
                <key>nibPath</key>
                <string>/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib</string>
            </dict>
        </dict>
    </array>
    <key>connectors</key>
    <dict/>
    <key>workflowMetaData</key>
    <dict>
        <key>serviceInputTypeIdentifier</key>
        <string>com.apple.Automator.text</string>
        <key>serviceOutputTypeIdentifier</key>
        <string>com.apple.Automator.nothing</string>
        <key>serviceProcessesInput</key>
        <integer>0</integer>
        <key>workflowTypeIdentifier</key>
        <string>com.apple.Automator.servicesMenu</string>
    </dict>
</dict>
</plist>
"""


def install_macos_quick_action() -> Path:
    """Create and install a macOS Quick Action (Service) workflow.

    After installation the user can select text in any app, right-click,
    and choose **Services → Lector: Read / Stop**.
    Invoking it while Lector is already playing stops playback.

    Returns the path to the installed ``.workflow`` bundle.
    """
    workflow_dir = (
        Path.home()
        / "Library"
        / "Services"
        / "Lector - Read or Stop.workflow"
        / "Contents"
    )
    workflow_dir.mkdir(parents=True, exist_ok=True)

    # Remove legacy workflow bundle if present.
    legacy = workflow_dir.parent.parent / "Read with Lector.workflow"
    if legacy.exists():
        shutil.rmtree(legacy)

    # Write Info.plist — required for macOS to register the service.
    info_plist_path = workflow_dir / "Info.plist"
    info_plist_path.write_text(_WORKFLOW_INFO_PLIST, encoding="utf-8")

    # Build the shell command.  Selected text arrives on stdin (inputMethod=0).
    # exec 2>/dev/null silences ALL stderr before Python even starts, so
    # Automator never sees output to display in an error dialog.
    # "|| true" ensures exit-code 0 so Automator never flags a failure.
    lector_bin = shutil.which("lector") or "lector"
    shell_command = (
        "exec 2>/dev/null\n"
        'export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"\n'
        f'"{lector_bin}" read || true'
    )

    wflow_xml = _WORKFLOW_PLIST.replace("__SHELL_COMMAND__", xml_escape(shell_command))
    wflow_path = workflow_dir / "document.wflow"
    wflow_path.write_text(wflow_xml, encoding="utf-8")

    # Tell macOS to re-scan services.
    bundle_root = wflow_path.parent.parent
    subprocess.run(
        [
            "/System/Library/Frameworks/CoreServices.framework/Frameworks/"
            "LaunchServices.framework/Support/lsregister",
            "-R", "-f", str(bundle_root),
        ],
        capture_output=True,
    )

    return bundle_root


def uninstall_macos_quick_action() -> Path | None:
    """Remove the Lector Quick Action (Service) workflow.

    Returns the path that was removed, or ``None`` if it was not installed.
    """
    bundle_root = (
        Path.home()
        / "Library"
        / "Services"
        / "Lector - Read or Stop.workflow"
    )
    if not bundle_root.exists():
        return None

    shutil.rmtree(bundle_root)
    return bundle_root
