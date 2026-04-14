#!/usr/bin/env bash
# PreToolUse hook: blocks git commit if pyproject.toml and stackr/__init__.py versions differ.
# Receives Claude tool-use JSON on stdin.

stdin=$(cat)
cmd=$(echo "$stdin" | jq -r '.tool_input.command // ""')

# Only act on git commit commands
echo "$cmd" | grep -q 'git commit' || exit 0

REPO=/Users/dominiclittler/deployerreplacement
PV=$(grep '^version = ' "$REPO/pyproject.toml" | sed 's/.*"\(.*\)".*/\1/')
IV=$(grep '__version__ = ' "$REPO/stackr/__init__.py" | sed 's/.*"\(.*\)".*/\1/')

if [ "$PV" != "$IV" ]; then
  printf '{"continue":false,"stopReason":"Version mismatch before commit: pyproject.toml=%s but stackr/__init__.py=%s — update both to match first."}\n' "$PV" "$IV"
  exit 0
fi

# Versions match — allow the commit
exit 0
