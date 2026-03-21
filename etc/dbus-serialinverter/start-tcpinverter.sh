#!/bin/bash
# Development helper: start the mock TCP server and run the driver against it.
# Bypasses serial-starter since TCP connections don't use /dev/ttyUSB*.
#
# Usage:
#   ./start-tcpinverter.sh                        # localhost:5020, normal scenario
#   ./start-tcpinverter.sh --scenario fault        # localhost:5020, fault scenario
#   ./start-tcpinverter.sh --port 5021             # custom port
#
# All arguments are passed through to samlex_tcp_server.py.
# Press Ctrl-C to stop both the server and the driver.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# In the release tarball, samlex_tcp_server.py is alongside the driver.
# In the source repo, it lives in tests/.
if [ -f "$SCRIPT_DIR/samlex_tcp_server.py" ]; then
    SERVER="$SCRIPT_DIR/samlex_tcp_server.py"
elif [ -f "$SCRIPT_DIR/../../tests/samlex_tcp_server.py" ]; then
    SERVER="$SCRIPT_DIR/../../tests/samlex_tcp_server.py"
else
    echo "Error: samlex_tcp_server.py not found"
    exit 1
fi

# Parse --host and --port from args (defaults match samlex_tcp_server.py)
HOST="localhost"
PORT="5020"
SERVER_ARGS=("$@")

while [ $# -gt 0 ]; do
    case "$1" in
        --host) HOST="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# Clean up server on exit
cleanup() {
    [ -n "${SERVER_PID:-}" ] && kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
}
trap cleanup EXIT

echo "Starting mock TCP server on ${HOST}:${PORT}..."
python "$SERVER" "${SERVER_ARGS[@]}" &
SERVER_PID=$!

# Wait for the server port to be listening (up to 10 seconds)
TRIES=0
while ! (echo > /dev/tcp/"$HOST"/"$PORT") 2>/dev/null; do
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge 20 ]; then
        echo "Error: Mock server not listening on ${HOST}:${PORT} after 10s."
        exit 1
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "Error: Mock server process exited."
        exit 1
    fi
    sleep 0.5
done

echo "Starting driver against tcp://${HOST}:${PORT}..."
python "$SCRIPT_DIR/dbus-serialinverter.py" "tcp://${HOST}:${PORT}"
