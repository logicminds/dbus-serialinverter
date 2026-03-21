#!/bin/bash
# Development helper: run the driver against a Modbus TCP inverter (or samlex_tcp_server.py).
# Bypasses serial-starter since TCP connections don't use /dev/ttyUSB*.
#
# Usage:
#   ./start-tcpinverter.sh localhost:5020
#   ./start-tcpinverter.sh 192.168.1.100:502

set -euo pipefail

ADDR="${1:?Usage: $0 <host:port>}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

exec python "$SCRIPT_DIR/dbus-serialinverter.py" "tcp://${ADDR}"
