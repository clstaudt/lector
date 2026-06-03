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

### uv (all platforms)

You need [uv](https://docs.astral.sh/uv/), a Python package manager.
It handles everything else (including Python itself) automatically.

<details>
<summary><strong>macOS</strong></summary>

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Or via [Homebrew](https://brew.sh/):

```bash
brew install uv
```

</details>

<details>
<summary><strong>Linux</strong></summary>

Install PortAudio (required by [sounddevice](https://python-sounddevice.readthedocs.io/) for playback):

```bash
sudo apt install libportaudio2 portaudio19-dev   # Debian / Ubuntu
```

For `lector read --clipboard`, install a clipboard provider:

```bash
sudo apt install xclip          # X11
sudo apt install xsel           # X11 (alternative)
sudo apt install wl-clipboard   # Wayland
```

Then install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

</details>

<details>
<summary><strong>Windows</strong></summary>

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

</details>

Restart your shell after installing so that the `uv` command is available.

## Install

```bash
uv tool install git+https://github.com/clstaudt/lector
```

Or from a local checkout:

```bash
uv tool install /path/to/lector
```

The first run downloads model files (~300 MB) to `~/.lector/models/`.

## Usage

```bash
# Read text directly
lector read "The quick brown fox jumps over the lazy dog."

# Read from the clipboard
lector read --clipboard

# Pipe text in
cat article.txt | lector read
```

Lector detects the language automatically and picks a matching voice.

### Player controls

| Key       | Action         |
| --------- | -------------- |
| `Space`   | Pause / resume |
| `q`       | Quit           |
| `r`       | Restart        |
| `← h`     | Previous chunk |
| `→ l`     | Next chunk     |
| `+`       | Speed up       |
| `-`       | Slow down      |

### Languages

Language is detected automatically by default (`--lang auto`).
Set it explicitly with `--lang`:

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
lector read "Bonjour, comment allez-vous ?"           # auto-detected
lector read --lang de "Guten Morgen, wie geht es Ihnen?"  # explicit
```

If a detected language is not supported, Lector falls back to English.

German uses a separate community model
([Kokoro-82M-ONNX-German-Martin](https://huggingface.co/huggingFresse/Kokoro-82M-ONNX-German-Martin)),
fetched automatically on first use (or in advance with
`lector download --german`).

### Voices

```bash
lector voices                 # all voices, grouped by language
lector voices --lang fr-fr    # only French voices
```

Pick a specific voice with `--voice` (this also implies the language):

```bash
lector read --voice af_nicole --speed 0.9 "Hello!"
```

See the full list at
[Kokoro-82M/VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).

## macOS: right-click integration

Add a **Quick Action** so *Read with Lector* appears in the right-click
Services menu:

```bash
lector install-service
```

Select text in any app → right-click → **Services** → **Read with Lector**.
You may need to enable it in
**System Settings → Keyboard → Keyboard Shortcuts → Services**.

## Commands

| Command                    | Description                          |
| -------------------------- | ------------------------------------ |
| `lector read`              | Read text aloud (arg / clipboard / stdin) |
| `lector voices`            | List available voices by language    |
| `lector download`          | Pre-download model files (~300 MB)   |
| `lector download --german` | Pre-download the German model        |
| `lector install-service`   | Install macOS Quick Action           |

Key `lector read` options: `--lang`, `--voice`, `--speed`.

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
