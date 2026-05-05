# Changelog

All notable changes to MMPipe are documented here.

## [Unreleased]

## [2.0.0] — 2026-05-05

### Added
- `shell/mmpick.sh` — macOS native file-picker (osascript) that emits MMP/1.0 envelopes
  with `X-MMP-Source` header; supports multi-file selection; works in bash and zsh
- `bridge/mmkitty.py` — non-destructive Kitty Graphics Protocol bridge; renders inline
  image thumbnails in Kitty terminal (PNG via f=100, JPEG via f=88, GIF/WebP via sips);
  passes original MMP/1.0 envelope downstream unchanged
- `tui/mmtui.py` — full-screen Textual TUI with File Browser, Pipeline Builder, and live
  Output panel; keyboard-driven pipeline assembly and execution
- `install.sh` — one-line installer that wires up all aliases and functions into
  `~/.zshrc` or `~/.bashrc`
- `__version__ = "2.0.0"` version string in `mm.py`
- v2 architecture section in README with ASCII art diagram and upgrade-path table

## [0.1.0] — 2026-05-05

### Added
- `mm.py` — core implementation of the Universal Media Pipe Protocol (UMPP)
  - `mcat` command: wraps binary files with `MMP/1.0` headers and streams to stdout
  - `analyze_vision` command: parses UMPP frames, calls Gemini, outputs plain UTF-8
  - Magic-byte fallback for pipes that bypass `mcat` (JPEG, PNG, GIF, WEBP)
  - Mock mode when `GEMINI_API_KEY` is not set
- `test_mm.py` — 19-test suite covering emit, protocol parsing, fallback sniffing, live API path, and CLI routing
- GitHub Actions workflow running tests on push across Python 3.10, 3.11, 3.12
- CI status badge in README
- Asciinema demo recording
- Logo (`assets/mmpipe-logo.jpg`)

### Fixed
- Gemini model updated from `gemini-1.5-flash` → `gemini-2.0-flash` → `gemini-2.5-flash` as older models were retired for new API keys
