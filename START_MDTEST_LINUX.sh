#!/bin/sh
# Start MDTest with a private virtual environment. No activation required.
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
cd "$ROOT" || exit 1
echo ""
echo "===================================================="
echo " MDTest - easy start (macOS/Linux)"
echo "===================================================="
# Prefer mature dependency-supported versions; Python 3.15 is supported as an option.
for CANDIDATE in python3.13 python3.12 python3.14 python3.15 python3.11 python3 python; do
  if command -v "$CANDIDATE" >/dev/null 2>&1; then
    if "$CANDIDATE" -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 15) else 1)' >/dev/null 2>&1; then
      exec "$CANDIDATE" "$ROOT/tools/launch_mdtest.py" "$@"
    fi
  fi
done
echo "Python 3.11 through 3.15 was not found."
echo "Install Python from https://www.python.org/downloads/ and run START again."
exit 2
