#!/usr/bin/env bash
# Stackr installer / uninstaller
# Install:   curl -fsSL https://raw.githubusercontent.com/djnw8fs748-eng/deployerreplacement/main/install.sh | bash
# Uninstall: curl -fsSL https://raw.githubusercontent.com/djnw8fs748-eng/deployerreplacement/main/install.sh | bash -s -- --uninstall

GITHUB_REPO="djnw8fs748-eng/deployerreplacement"

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[stackr]${NC} $*"; }
warn()    { echo -e "${YELLOW}[stackr]${NC} $*"; }
error()   { echo -e "${RED}[stackr]${NC} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

if [[ "${1:-}" == "--uninstall" ]]; then
    info "Uninstalling stackr..."

    # Remove the pipx-managed package
    if command -v pipx >/dev/null 2>&1 && pipx list 2>/dev/null | grep -q "package stackr"; then
        pipx uninstall stackr
        info "pipx package removed."
    else
        warn "stackr pipx package not found — skipping."
    fi

    # Remove state directory (~/.stackr)
    STACKR_DIR="$HOME/.stackr"
    if [[ -d "$STACKR_DIR" ]]; then
        echo ""
        echo -e "${YELLOW}[stackr]${NC} Found data directory: $STACKR_DIR"
        echo "  This contains your app state, catalog, and any generated secrets."
        printf "  Remove it? [y/N] "
        read -r REPLY </dev/tty
        if [[ "$REPLY" =~ ^[Yy]$ ]]; then
            rm -rf "$STACKR_DIR"
            info "Removed $STACKR_DIR"
        else
            warn "Kept $STACKR_DIR"
        fi
    fi

    # Remind about .stackr.env files left in project directories
    echo ""
    warn "Note: any .stackr.env files in your project directories were not removed."
    warn "      Delete them manually if you no longer need the secrets they contain."
    echo ""
    info "Stackr uninstalled."
    exit 0
fi

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

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
    # Prefer the system package manager (avoids PEP 668 "externally-managed-environment"
    # errors on Debian 12+ / Ubuntu 22.04+).  Fall back to pip only as a last resort.
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y -qq pipx
    elif command -v apt >/dev/null 2>&1; then
        sudo apt install -y -qq pipx
    elif command -v brew >/dev/null 2>&1; then
        brew install pipx --quiet
    else
        # Last resort: pip with --break-system-packages (Python 3.11+ flag)
        python3 -m pip install --user pipx --quiet --break-system-packages 2>/dev/null \
            || python3 -m pip install --user pipx --quiet
    fi
    export PATH="$PATH:$HOME/.local/bin"
fi

# --- Ensure pipx bin dir is in PATH (writes to shell rc files) ---
python3 -m pipx ensurepath --force >/dev/null 2>&1 || true
export PATH="$PATH:$HOME/.local/bin"

# --- Install stackr ---
REPO_URL="git+https://github.com/${GITHUB_REPO}.git"

info "Installing stackr via pipx from GitHub..."
if pipx list 2>/dev/null | grep -q "package stackr"; then
    info "Existing installation found — upgrading..."
    pipx upgrade --pip-args="--quiet" stackr
else
    pipx install --pip-args="--quiet" "$REPO_URL"
fi

STACKR_VERSION=$(stackr --version 2>/dev/null || echo "unknown")
info "Stackr ${STACKR_VERSION} installed successfully."

echo ""
echo "  Next steps:"
echo "    stackr init       # interactive setup wizard"
echo "    stackr list       # browse available apps"
echo "    stackr deploy     # deploy your stack"
echo "    stackr ui         # open the terminal UI"
echo "    stackr web        # start the web UI"
echo ""

# --- PATH reload reminder ---
# The installer runs in a subshell so PATH changes don't propagate to the
# parent shell.  Tell the user to reload if stackr isn't findable yet.
if ! command -v stackr >/dev/null 2>&1; then
    echo -e "${YELLOW}[stackr]${NC} 'stackr' is not yet on your PATH."
    echo ""
    echo "  Run one of the following to activate it in your current shell:"
    echo ""
    echo "    source ~/.bashrc       # bash"
    echo "    source ~/.zshrc        # zsh"
    echo "    exec \$SHELL            # reload current shell"
    echo ""
    echo "  Or open a new terminal — stackr will be available automatically."
    echo ""
fi
