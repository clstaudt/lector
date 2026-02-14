# Lector

**Read text aloud with high-quality neural TTS — from clipboard, stdin, or argument.**

Lector wraps [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) in a
simple CLI.  Audio is streamed chunk-by-chunk so reading starts immediately,
even for long texts.

## Quick start

```bash
# Install with uv (recommended)
uv sync

# Download model files (~300 MB, one-time)
uv run lector download

# Read from clipboard
pbpaste | uv run lector read

# Read from argument
uv run lector read "The quick brown fox jumps over the lazy dog."

# Read clipboard directly
uv run lector read --clipboard

# Adjust voice and speed
cat article.txt | uv run lector read --voice af_nicole --speed 0.9
```

Once installed globally (`uv tool install .`), drop the `uv run` prefix:

```bash
lector read --clipboard
lector read "Hello, world!"
echo "Some text" | lector read
```

## Voices

```bash
lector voices
```

Popular English voices: `af_heart`, `af_nicole`, `af_sarah`, `af_sky`,
`am_michael`.  See the full list at
[Kokoro-82M/VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).

## macOS right-click integration

Lector can install itself as a **Quick Action** (Service) so that
*Read with Lector* appears in the right-click → Services menu, just like
the built-in "Start Speaking" option:

```bash
lector install-service
```

After installation:

1. Select text in any app.
2. Right-click → **Services** → **Read with Lector**.
3. (First time you may need to enable it in
   **System Settings → Keyboard → Keyboard Shortcuts → Services**.)

## Commands

| Command             | Description                                 |
| ------------------- | ------------------------------------------- |
| `lector read`       | Read text aloud (arg / clipboard / stdin)   |
| `lector voices`     | List available voice names                  |
| `lector download`   | Download model files                        |
| `lector install-service` | Install macOS Quick Action             |

## Development

```bash
# Clone & set up
git clone <repo-url> && cd lector
uv sync

# Run tests
uv run pytest

# Run lector from source
uv run lector read "Hello!"
```

## License

MIT
