#!/usr/bin/env bash
#
# mmpick — macOS native file picker that emits MMP/1.0 envelopes.
#
# MMP/1.0 contract implemented:
#   Opens a native macOS file-picker dialog via osascript. For each selected
#   file, writes one UMPP envelope to stdout:
#
#     MMP/1.0\n
#     Content-Type: <mime>\n
#     Content-Length: <bytes>\n
#     X-MMP-Source: <filename>\n
#     \n
#     <binary payload>
#
#   Multi-file selections emit envelopes concatenated in selection order.
#   Works in bash and zsh.
#
# Usage (source or execute directly):
#   mmpick | analyze_vision "describe this"
#   mmpick | mmkitty | analyze_vision | grep red
#
# Install: source shell/mmpick.sh  (adds mmpick to your shell session)

# ---------------------------------------------------------------------------
# Portable script-dir detection (bash + zsh)
# ---------------------------------------------------------------------------
if [ -n "${BASH_SOURCE[0]}" ]; then
    _MMPICK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    _MMPICK_DIR="$(cd "$(dirname "$0")" && pwd)"
fi

# ---------------------------------------------------------------------------
# Emit one MMP/1.0 envelope for a single file
# Uses inline Python so binary headers + payload are written safely.
# ---------------------------------------------------------------------------
_mmpick_emit_one() {
    local file="$1"
    local mime
    mime=$(file --mime-type -b "$file" 2>/dev/null || echo "application/octet-stream")
    # Strip any trailing whitespace/newline from file output
    mime="${mime%$'\n'}"
    mime="${mime%$'\r'}"

    python3 - "$file" "$mime" <<'PYEOF'
import sys
import os

path = sys.argv[1]
mime = sys.argv[2]
size = os.path.getsize(path)
name = os.path.basename(path)

MAGIC = b"MMP/1.0\n"
sys.stdout.buffer.write(MAGIC)
sys.stdout.buffer.write(f"Content-Type: {mime}\n".encode('utf-8'))
sys.stdout.buffer.write(f"Content-Length: {size}\n".encode('utf-8'))
sys.stdout.buffer.write(f"X-MMP-Source: {name}\n".encode('utf-8'))
sys.stdout.buffer.write(b"\n")
with open(path, 'rb') as f:
    while chunk := f.read(8192):
        sys.stdout.buffer.write(chunk)
sys.stdout.buffer.flush()
PYEOF
}

# ---------------------------------------------------------------------------
# Open macOS native file-picker; return newline-separated POSIX paths
# ---------------------------------------------------------------------------
_mmpick_dialog() {
    osascript <<'APPLESCRIPT'
try
    set theFiles to choose file with multiple selections allowed
    set output to ""
    repeat with aFile in theFiles
        set output to output & POSIX path of aFile & linefeed
    end repeat
    return output
on error
    return ""
end try
APPLESCRIPT
}

# ---------------------------------------------------------------------------
# Main entry point (also callable as a function when sourced)
# ---------------------------------------------------------------------------
mmpick() {
    local files
    files=$(_mmpick_dialog 2>/dev/null)

    if [ -z "$files" ]; then
        printf "mmpick: no file selected\n" >&2
        return 1
    fi

    local file
    while IFS= read -r file; do
        [ -z "$file" ] && continue
        if [ ! -f "$file" ]; then
            printf "mmpick: file not found: %s\n" "$file" >&2
            continue
        fi
        _mmpick_emit_one "$file"
    done <<< "$files"
}

# Run if executed directly (not sourced)
if [ "${BASH_SOURCE[0]}" = "$0" ] || [ "$(basename -- "$0")" = "mmpick.sh" ]; then
    mmpick "$@"
fi
