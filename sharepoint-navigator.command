#!/bin/bash
# SharePoint Navigator launcher for macOS. Double-click it in Finder or run it in Terminal.
#   1. Creates or repairs .venv and installs requirements.txt when it changes.
#   2. Starts the Python service (tenant: the only <tenant>_clientid.txt here, else the saved one, else it asks).
#   3. Opens the app in the browser once the service answers.
# Options: --no-open (don't open the browser). Port: SHAREPOINT_NAVIGATOR_PORT (default 8765).

set -u
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

PORT="${SHAREPOINT_NAVIGATOR_PORT:-8765}"
URL="http://127.0.0.1:${PORT}/"
VENV_PY=".venv/bin/python"
STAMP=".venv/.requirements.sha256"
OPEN_BROWSER=1
[ "${1:-}" = "--no-open" ] && OPEN_BROWSER=0

fail() {
    echo
    echo "Error: $*"
    # Keep a double-clicked Terminal window open long enough to read the error.
    [ -t 0 ] && read -r -p "Press Enter to close." _
    exit 1
}

is_navigator_running() {
    curl -s -m 2 -D - -o /dev/null "$URL" 2>/dev/null | grep -qi '^server: SharePointNavigator'
}

open_url() {
    [ "$OPEN_BROWSER" = 1 ] && open "$URL"
}

# Already running? Just open it.
if is_navigator_running; then
    echo "SharePoint Navigator is already running at $URL"
    echo "(To load code changes, stop it with the app's Stop service button and run this again.)"
    open_url
    exit 0
fi

# 1. Python environment
venv_works() {
    [ -x "$VENV_PY" ] && "$VENV_PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

if ! venv_works; then
    if [ -e .venv ]; then
        backup=".venv-broken-$(date +%Y%m%d-%H%M%S)"
        echo "The existing .venv is missing, broken or older than Python 3.11. Moving it to $backup."
        mv .venv "$backup" || fail "Could not move the old .venv aside."
    fi
    echo "Creating .venv..."
    if command -v uv >/dev/null 2>&1; then
        uv python install 3.13 >/dev/null 2>&1 || true
        uv venv --seed --python 3.13 .venv || fail "uv could not create the virtual environment."
    else
        PY=""
        for candidate in python3.13 python3.12 python3.11 python3; do
            if command -v "$candidate" >/dev/null 2>&1 &&
               "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
                PY="$candidate"; break
            fi
        done
        [ -n "$PY" ] || fail "Python 3.11 or later was not found. Install uv (https://docs.astral.sh/uv/) or Python from python.org, then run this again."
        "$PY" -m venv .venv || fail "Could not create the virtual environment."
    fi
fi

wanted="$(shasum -a 256 requirements.txt | cut -d' ' -f1)"
if [ "$(cat "$STAMP" 2>/dev/null)" != "$wanted" ] ||
   ! "$VENV_PY" -c 'import msal, msal_extensions, requests' 2>/dev/null; then
    echo "Installing Python packages..."
    "$VENV_PY" -m pip install --disable-pip-version-check -q -r requirements.txt ||
        fail "Package installation failed. Check the network connection and try again."
    echo "$wanted" > "$STAMP"
fi

# 2. Tenant: use the only <tenant>_clientid.txt here; otherwise the app asks.
TENANT=""
clientid_files=( *_clientid.txt )
if [ "${#clientid_files[@]}" -eq 1 ] && [ -f "${clientid_files[0]}" ]; then
    TENANT="${clientid_files[0]%_clientid.txt}"
fi

# 3. Open the browser once the service is up. The launcher opens it, so stop Python from opening it too.
waiter_pid=""
if [ "$OPEN_BROWSER" = 1 ]; then
    (
        # Allow up to 15 minutes for a first-time device-code sign-in.
        for _ in $(seq 1 900); do
            kill -0 $$ 2>/dev/null || exit 0
            if is_navigator_running; then open "$URL"; exit 0; fi
            sleep 1
        done
    ) &
    waiter_pid=$!
fi
trap '[ -n "$waiter_pid" ] && kill "$waiter_pid" 2>/dev/null' EXIT

echo "Starting SharePoint Navigator${TENANT:+ for $TENANT}. Closing its browser tab stops it."
BROWSER=true "$VENV_PY" sharepoint-navigator.py ${TENANT:+"$TENANT"}
status=$?
[ "$status" -ne 0 ] && fail "SharePoint Navigator stopped with an error (exit $status). See the messages above."
exit 0
