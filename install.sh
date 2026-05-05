#!/usr/bin/env bash
#
# MMPipe v2 installer
# Sets up mcat, analyze_vision, mmpick, mmkitty, and mmtui aliases/functions.
#
# Usage:
#   bash install.sh            # detects ~/.zshrc or ~/.bashrc automatically
#   bash install.sh ~/.zshrc   # explicit target rc file

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MMPY="$REPO_DIR/mm.py"
MMKITTY="$REPO_DIR/bridge/mmkitty.py"
MMTUI="$REPO_DIR/tui/mmtui.py"
MMPICK="$REPO_DIR/shell/mmpick.sh"

# ---------------------------------------------------------------------------
# Detect shell rc file
# ---------------------------------------------------------------------------
if [ -n "${1:-}" ]; then
    RC_FILE="$1"
elif [ -n "${ZSH_VERSION:-}" ] || [ "$(basename "$SHELL")" = "zsh" ]; then
    RC_FILE="$HOME/.zshrc"
else
    RC_FILE="$HOME/.bashrc"
fi

echo "MMPipe v2 installer"
echo "  Repo:    $REPO_DIR"
echo "  RC file: $RC_FILE"
echo ""

# ---------------------------------------------------------------------------
# Make scripts executable
# ---------------------------------------------------------------------------
chmod +x "$MMPY"
chmod +x "$MMKITTY"
chmod +x "$MMTUI"
chmod +x "$MMPICK"
echo "✓ Scripts marked executable"

# ---------------------------------------------------------------------------
# Optional: install textual for mmtui
# ---------------------------------------------------------------------------
if ! python3 -c "import textual" 2>/dev/null; then
    echo ""
    read -r -p "Install textual for mmtui? (pip install textual) [y/N] " ans
    if [[ "${ans,,}" == "y" ]]; then
        pip install textual
        echo "✓ textual installed"
    else
        echo "  Skipping textual — mmtui will not work until you run: pip install textual"
    fi
else
    echo "✓ textual already installed"
fi

# ---------------------------------------------------------------------------
# Write shell config block
# ---------------------------------------------------------------------------
BLOCK_START="# >>> MMPipe v2 >>>"
BLOCK_END="# <<< MMPipe v2 <<<"

# Remove any existing MMPipe block to avoid duplicates
if grep -q "$BLOCK_START" "$RC_FILE" 2>/dev/null; then
    # Use Python for portable in-place edit (works on macOS and Linux)
    python3 - "$RC_FILE" "$BLOCK_START" "$BLOCK_END" <<'PYEOF'
import sys
rc_path, start, end = sys.argv[1], sys.argv[2], sys.argv[3]
with open(rc_path) as f:
    lines = f.readlines()
out, inside = [], False
for line in lines:
    if line.strip() == start:
        inside = True
    if not inside:
        out.append(line)
    if line.strip() == end:
        inside = False
with open(rc_path, 'w') as f:
    f.writelines(out)
PYEOF
    echo "  Removed existing MMPipe block from $RC_FILE"
fi

cat >> "$RC_FILE" <<SHELLBLOCK

$BLOCK_START
# MMPipe v2 — https://github.com/bretkerr/MMPipe
export MMPY="$MMPY"

# Core v1 commands
alias mcat="python3 $MMPY mcat"
alias analyze_vision="python3 $MMPY analyze_vision"

# v2: macOS file picker (source the script to get the mmpick function)
source "$MMPICK"

# v2: Kitty Graphics Protocol bridge
alias mmkitty="python3 $MMKITTY"

# v2: Full-screen TUI (requires: pip install textual)
alias mmtui="python3 $MMTUI"
$BLOCK_END
SHELLBLOCK

echo "✓ Shell aliases written to $RC_FILE"
echo ""
echo "Run this to activate in your current session:"
echo "  source $RC_FILE"
echo ""
echo "Quick test (mock mode, no API key required):"
echo "  mcat assets/mmpipe-logo.jpg | analyze_vision"
