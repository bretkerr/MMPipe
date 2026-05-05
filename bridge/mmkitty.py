#!/usr/bin/env python3
"""
mmkitty — Kitty Graphics Protocol bridge for MMP/1.0 streams.

MMP/1.0 contract implemented:
  Reads exactly one UMPP envelope from stdin. If the terminal is Kitty
  ($TERM == xterm-kitty) and the Content-Type is image/*, renders an inline
  thumbnail via the Kitty Graphics Protocol (APC escape sequence). Falls back
  to a text summary line on stderr in non-Kitty terminals.

  ALWAYS writes the original MMP/1.0 envelope to stdout unchanged so
  downstream consumers (analyze_vision, grep, etc.) receive the same stream
  they would have seen without mmkitty in the chain.

Supported formats (sent natively to Kitty):
  image/png   — f=100 (PNG encoding)
  image/jpeg  — f=88  (JPEG encoding, Kitty ≥ 0.20)
  image/gif   — first frame only, rendered as PNG via sips if available
  image/webp  — rendered as PNG via sips if available

Usage:
  mcat photo.jpg | mmkitty | analyze_vision "describe this"
  mcat photo.jpg | mmkitty | analyze_vision | grep red
  mmpick       | mmkitty | analyze_vision

Requirements: Python 3.9+, Kitty terminal (optional — degrades gracefully)
"""

import sys
import os
import base64
import subprocess
import tempfile

PROTOCOL_MAGIC = b"MMP/1.0\n"
KITTY_CHUNK_SIZE = 4096
PREVIEW_COLS = 20  # terminal columns wide for the inline preview


# ---------------------------------------------------------------------------
# MMP/1.0 envelope reader
# ---------------------------------------------------------------------------

def read_envelope(stream):
    """
    Read one MMP/1.0 envelope from stream.
    Returns (headers: dict | None, payload: bytes | None, raw: bytes).
    raw is the exact bytes consumed — write it downstream for pass-through.
    """
    raw = b""
    first_line = stream.readline()
    raw += first_line

    if first_line != PROTOCOL_MAGIC:
        # Not a UMPP stream — slurp the rest and pass through unchanged
        rest = stream.read()
        return None, None, raw + rest

    headers = {}
    while True:
        line = stream.readline()
        raw += line
        if line == b"\n":
            break
        key, _, val = line.decode("utf-8").partition(":")
        headers[key.strip().lower()] = val.strip()

    length = int(headers.get("content-length", 0))
    payload = stream.read(length)
    raw += payload

    return headers, payload, raw


# ---------------------------------------------------------------------------
# Optional JPEG/WebP/GIF → PNG conversion via macOS sips (zero extra deps)
# ---------------------------------------------------------------------------

def _sips_to_png(data: bytes, in_suffix: str) -> bytes | None:
    """Convert image bytes to PNG using macOS sips. Returns None if unavailable."""
    try:
        with tempfile.NamedTemporaryFile(suffix=in_suffix, delete=False) as src:
            src.write(data)
            src_path = src.name
        dst_path = src_path + ".png"
        result = subprocess.run(
            ["sips", "-s", "format", "png", src_path, "--out", dst_path],
            capture_output=True
        )
        if result.returncode != 0:
            return None
        with open(dst_path, "rb") as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return None
    finally:
        try:
            os.unlink(src_path)
        except OSError:
            pass
        try:
            os.unlink(dst_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Kitty Graphics Protocol renderer
# ---------------------------------------------------------------------------

def _send_kitty_chunks(encoded: str, fmt: int, cols: int) -> None:
    """Write chunked Kitty APC escape sequences to stdout."""
    chunks = [encoded[i:i + KITTY_CHUNK_SIZE]
              for i in range(0, len(encoded), KITTY_CHUNK_SIZE)]

    for i, chunk in enumerate(chunks):
        more = 0 if i == len(chunks) - 1 else 1
        if i == 0:
            params = f"a=T,f={fmt},m={more},c={cols},q=2"
        else:
            params = f"m={more},q=2"
        sys.stdout.write(f"\x1b_G{params};{chunk}\x1b\\")

    sys.stdout.write("\n")
    sys.stdout.flush()


def render_kitty(data: bytes, mime_type: str) -> None:
    """Render image inline using the Kitty Graphics Protocol."""

    if mime_type == "image/png":
        encoded = base64.standard_b64encode(data).decode("ascii")
        _send_kitty_chunks(encoded, fmt=100, cols=PREVIEW_COLS)

    elif mime_type == "image/jpeg":
        # f=88: native JPEG support in Kitty ≥ 0.20
        encoded = base64.standard_b64encode(data).decode("ascii")
        _send_kitty_chunks(encoded, fmt=88, cols=PREVIEW_COLS)

    elif mime_type in ("image/gif", "image/webp"):
        # Convert first frame to PNG via sips (macOS built-in)
        suffix = ".gif" if mime_type == "image/gif" else ".webp"
        png_data = _sips_to_png(data, suffix)
        if png_data:
            encoded = base64.standard_b64encode(png_data).decode("ascii")
            _send_kitty_chunks(encoded, fmt=100, cols=PREVIEW_COLS)
        else:
            sys.stderr.write(
                f"[mmkitty] {mime_type}: sips not available; "
                "install Pillow for cross-platform conversion\n"
            )

    else:
        sys.stderr.write(f"[mmkitty] unsupported image format for inline render: {mime_type}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if sys.stdin.isatty():
        sys.stderr.write(
            "Error: Expected piped data (e.g., mcat image.png | mmkitty).\n"
        )
        sys.exit(1)

    headers, payload, raw = read_envelope(sys.stdin.buffer)

    if headers is None:
        # Non-UMPP input — pass through silently
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
        return

    mime_type = headers.get("content-type", "application/octet-stream")
    source = headers.get("x-mmp-source", "<unknown>")
    size_kb = len(payload) / 1024

    if mime_type.startswith("image/"):
        if os.environ.get("TERM") == "xterm-kitty":
            render_kitty(payload, mime_type)
        else:
            sys.stderr.write(
                f"[mmkitty] {source}: {mime_type} {size_kb:.1f} KB "
                "(open in Kitty terminal for inline preview)\n"
            )
    else:
        sys.stderr.write(
            f"[mmkitty] {source}: {mime_type} — not an image, skipping render\n"
        )

    # Non-destructive: emit original envelope unchanged for downstream consumers
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
