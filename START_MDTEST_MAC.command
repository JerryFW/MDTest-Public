#!/bin/sh
# macOS: launch with a compatible Python, then create a private environment.
# If Gatekeeper blocks double-click: open Terminal, cd to this folder, run:
#   sh START_MDTEST_MAC.command
set -u
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
cd "$ROOT" || exit 1
printf '\n====================================================\n MDTest - Easy Start for macOS\n====================================================\n'
# Prefer mature scientific versions; accept Python 3.15 when it is installed.
for CANDIDATE in python3.13 python3.12 python3.14 python3.15 python3.11 python3 python; do
  if command -v "$CANDIDATE" >/dev/null 2>&1; then
    if "$CANDIDATE" -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,15) else 1)' >/dev/null 2>&1; then
      exec "$CANDIDATE" "$ROOT/tools/launch_mdtest.py" "$@"
    fi
  fi
done
printf '\nNo suitable Python was found for the MDTest Mac launcher.\n'
printf 'Recommended: install Python 3.13 or 3.12 from https://www.python.org/downloads/macos/\n'
printf 'Python 3.15 is recognized, but full MDTest/Jupyter testing on 3.15 is pending.\n'
printf 'Read docs/MAC_START_GUIDE.html for steps and troubleshooting.\n'
exit 2
