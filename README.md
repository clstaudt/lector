# Lector

**Read text aloud with high-quality neural TTS — from clipboard, stdin, or argument.**

> [!WARNING]
> Lector is in early development. Expect rough edges, breaking changes, and missing features.

Lector wraps [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) in a
simple CLI with an interactive player.  Audio is streamed chunk-by-chunk so
reading starts immediately, even for long texts.

<p align="center">
  <img src="img/terminal-screenshot.png" alt="Lector player UI" width="700">
</p>

## Prerequisites

You need [uv](https://docs.astral.sh/uv/), a Python package manager.
It handles everything else (including Python itself) automatically.

**Install uv** — open **Terminal** (⌘ Space → type "Terminal" → Enter) and run:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Or via [Homebrew](https://brew.sh/):

```bash
brew install uv
```

Close and reopen Terminal so the `uv` command is available.

### Linux: PortAudio

Lector uses [sounddevice](https://python-sounddevice.readthedocs.io/) for audio
playback, which requires the PortAudio library.  On Debian / Ubuntu:

```bash
sudo apt install libportaudio2 portaudio19-dev
```

On macOS, PortAudio is bundled with the sounddevice wheel — no extra step needed.

### Linux: Clipboard

For `lector read --clipboard` to work on Linux, install one of:

```bash
sudo apt install xclip          # X11
sudo apt install xsel           # X11 (alternative)
sudo apt install wl-clipboard   # Wayland
```

## Install

```bash
uv tool install git+https://github.com/clstaudt/lector
```

Or, if you have the source code locally:

```bash
uv tool install /path/to/lector
```

This installs `lector` as a system-wide command.  The first time you
use it, model files (~300 MB) are downloaded automatically to
`~/.lector/models/`.

## Usage

```bash
# Read text directly
lector read "The quick brown fox jumps over the lazy dog."

# Read from the clipboard
lector read --clipboard

# Pipe text in
pbpaste | lector read
cat article.txt | lector read
```

Lector detects the language of the text automatically and picks a
matching voice — just paste and go.

### Player controls

While audio is playing, use these keys:

| Key       | Action  |
| --------- | ------- |
| `Space`   | Pause / resume |
| `q`       | Quit    |
| `r`       | Restart |
| `← h`     | Previous chunk |
| `→ l`     | Next chunk |
| `+`       | Speed up  |
| `-`       | Slow down |

### Languages

Lector detects the language of the input text automatically (the default
`--lang auto`) and selects a suitable voice.  You can also set the
language explicitly with `--lang`:

| `--lang` | Language           | Default voice |
| -------- | ------------------ | ------------- |
| `auto`   | Auto-detect (default) | —          |
| `en-us`  | English (US)       | `af_sky`      |
| `en-gb`  | English (GB)       | `bf_emma`     |
| `es`     | Spanish            | `ef_dora`     |
| `fr-fr`  | French             | `ff_siwis`    |
| `hi`     | Hindi              | `hf_alpha`    |
| `it`     | Italian            | `if_sara`     |
| `ja`     | Japanese           | `jf_alpha`    |
| `pt-br`  | Portuguese (BR)    | `pf_dora`     |
| `zh`     | Chinese (Mandarin) | `zf_xiaobei`  |
| `de`     | German             | `martin`      |

```bash
# Auto-detected — no flags needed
lector read "Bonjour, comment allez-vous ?"

# Force a language
lector read --lang de "Guten Morgen, wie geht es Ihnen?"
```

If a detected language is not supported, Lector warns and falls back to
English.

German uses a separate community model
([Kokoro-82M-ONNX-German-Martin](https://huggingface.co/huggingFresse/Kokoro-82M-ONNX-German-Martin)),
fetched automatically on first use (or in advance with
`lector download --german`).

### Voices

```bash
lector voices                 # all voices, grouped by language
lector voices --lang fr-fr    # only French voices
```

Popular English voices: `af_heart`, `af_nicole`, `af_sarah`, `af_sky`,
`am_michael`.  Pick one with `--voice` (this also implies the language):

```bash
lector read --voice af_nicole --speed 0.9 "Hello!"
```

See the full list at
[Kokoro-82M/VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).

## macOS right-click integration

Add a **Quick Action** so *Read with Lector* appears in the right-click
Services menu — just like the built-in "Start Speaking":

```bash
lector install-service
```

Then:

1. Select text in any app.
2. Right-click → **Services** → **Read with Lector**.
3. (First time you may need to enable it in
   **System Settings → Keyboard → Keyboard Shortcuts → Services**.)

## Commands

| Command                  | Description                                       |
| ------------------------ | ------------------------------------------------- |
| `lector read`            | Read text aloud (arg / clipboard / stdin)         |
| `lector voices`          | List available voices, grouped by language        |
| `lector download`        | Pre-download model files (~300 MB)                |
| `lector download --german` | Pre-download the German model                   |
| `lector install-service` | Install macOS Quick Action                        |

Useful `lector read` options: `--lang` (language code or `auto`),
`--voice`, `--speed`.

## Updating

```bash
uv tool upgrade lector
```

## Uninstall

```bash
uv tool uninstall lector
rm -rf ~/.lector   # remove downloaded models
```

## Development

```bash
git clone <repo-url> && cd lector
uv sync
uv run lector read "Hello!"
uv run pytest
```

## License

GPL-3.0-or-later
