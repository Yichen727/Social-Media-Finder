#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
if [[ -x ".venv/bin/python" ]]; then
    ".venv/bin/python" bootstrap.py "$@"
    status=$?
elif command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'; then
    python3 bootstrap.py "$@"
    status=$?
else
    echo "Python 3.11 or newer was not found."
    echo "Install it from https://www.python.org/downloads/macos/, then launch again."
    status=1
fi
if [[ $status -ne 0 ]]; then
    echo "Startup failed. Read the error above. See README.md for help."
    read -r -p "Press Return to close this window… "
fi
exit "$status"
