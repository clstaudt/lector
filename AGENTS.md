# Coding Agent Instructions

## Project overview

**Lector** is a CLI tool that reads text aloud using neural TTS
([kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx)).  It streams
audio chunk-by-chunk through an interactive terminal player built with Rich and
sounddevice.

## Tooling

| Concern | Tool |
|---------|------|
| Package / env manager | **uv** — do **not** use `pip` or `conda` directly |
| Build backend | Hatchling (`src` layout: `src/lector/`) |
| Test runner | pytest — run with `uv run pytest tests/ -v` |
| Linter / formatter | Ruff — run with `uv run ruff check --fix . && uv run ruff format .` |
| Pre-commit hooks | pre-commit — config in `.pre-commit-config.yaml` |

### Useful commands

```bash
uv run pytest tests/ -v           # run tests
uv run ruff check --fix .         # lint + auto-fix
uv run ruff format .              # format
uv run pre-commit run --all-files # run all pre-commit hooks
uv run lector read --clipboard    # run the app
```

## Architecture

```
src/lector/
  cli.py            # Typer CLI (entry point: lector.cli:app)
  tts.py            # Kokoro engine wrapper, model download, player factory
  player.py         # AudioPlayer — threaded TTS generation + sounddevice playback
  ui.py             # Rich interactive UI, keyboard handling, headless mode
  macos_service.py  # macOS Quick Action installer
  utils.py          # Clipboard / stdin helpers
```

Key design:
- A background **generation worker** thread produces audio chunks ahead of the
  playback cursor (look-ahead buffer).
- A **sounddevice callback** on the audio thread consumes the buffer.
- The two communicate via a shared numpy buffer protected by a lock and a
  threading event (`_gen_wakeup`).

## Python style rules

Follow these conventions in **all** code — source and tests:

1. **Docstrings are mandatory** on every public module, class, and function.
   Use imperative mood (`"Return …"` not `"Returns …"`).
2. **No imports inside function bodies.** All imports go at module level.
3. **Type hints** on all function signatures (parameters and return types).
4. Use `from __future__ import annotations` at the top of every module for
   PEP 604 / PEP 563 style annotations.
5. Prefer **`pathlib.Path`** over `os.path`.
6. Constants are `UPPER_SNAKE_CASE`; classes `PascalCase`; everything else
   `lower_snake_case`.
7. Keep functions short and focused — if a function exceeds ~40 lines, consider
   splitting it.
8. Use **`# noqa: XXXX`** only when truly necessary, with a comment explaining why.

## Testing conventions

- Tests live in `tests/` and mirror the source module names (`test_player.py`
  tests `player.py`).
- Shared fixtures go in `tests/conftest.py`.
- Hardware boundaries (sounddevice, filesystem, subprocess) are mocked at the
  narrowest possible point.
- Run the full suite before committing: `uv run pytest tests/ -v`.
