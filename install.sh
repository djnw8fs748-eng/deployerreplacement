#!/usr/bin/env bash
# Stackr installer
# Usage: curl -fsSL https://raw.githubusercontent.com/your-org/stackr/main/install.sh | bash

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[stackr]${NC} $*"; }
warn()    { echo -e "${YELLOW}[stackr]${NC} $*"; }
error()   { echo -e "${RED}[stackr]${NC} $*" >&2; exit 1; }

# --- Requirements ---
command -v docker >/dev/null 2>&1 || error "Docker is required but not installed."
command -v python3 >/dev/null 2>&1 || error "Python 3.11+ is required but not installed."

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [[ "$PYTHON_MAJOR" -lt 3 || ("$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 11) ]]; then
    error "Python 3.11+ is required. Found: $PYTHON_VERSION"
fi

info "Python $PYTHON_VERSION detected."

# --- Install pipx if needed ---
if ! command -v pipx >/dev/null 2>&1; then
    info "Installing pipx..."
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath
    export PATH="$PATH:$HOME/.local/bin"
fi

# --- Install stackr ---
info "Installing stackr via pipx..."
pipx install stackr 2>/dev/null || pipx upgrade stackr

STACKR_VERSION=$(stackr --version 2>/dev/null || echo "unknown")
info "Stackr $STACKR_VERSION installed successfully."

echo ""
echo "  Next steps:"
echo "    stackr init       # interactive setup wizard"
echo "    stackr list       # browse available apps"
echo "    stackr deploy     # deploy your stack"
echo ""
