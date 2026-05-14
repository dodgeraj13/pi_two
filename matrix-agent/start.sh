#!/bin/bash
# start.sh — WiFi provisioning wrapper for the Matrix agent
#
# Usage:
#   bash start.sh            (from any directory)
#   ./start.sh               (after chmod +x start.sh on Linux/Pi)
#
# NOTE: chmod +x cannot be applied on Windows. When deploying to the Pi,
# run:  chmod +x /path/to/matrix-agent/start.sh
# or add it to setup.sh.
#
# What this does:
#   1. Runs wifi_setup.py — if offline, creates a hotspot and waits for
#      the user to provision credentials. Exits 0 when online.
#   2. Then starts agent.py (replacing this process via exec).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[start] Checking WiFi connectivity..."
python3 "$SCRIPT_DIR/wifi_setup.py" || true

echo "[start] Starting matrix agent..."
exec python3 "$SCRIPT_DIR/agent.py"
