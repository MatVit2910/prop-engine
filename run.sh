#!/usr/bin/env bash
set -e

# Change directory to project root
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

export PYTHONPATH="$PROJECT_DIR"

PYTHON_BIN="$PROJECT_DIR/.venv/bin/python3"
STREAMLIT_BIN="$PROJECT_DIR/.venv/bin/streamlit"

if [ ! -f "$PYTHON_BIN" ]; then
    echo "Error: Python binary not found at $PYTHON_BIN"
    exit 1
fi

echo "=========================================================="
echo " 🏀 Starting Live NBA Player Props Engine & Dashboard"
echo "=========================================================="

# Cleanup function to kill child processes on Ctrl+C or exit
cleanup() {
    echo ""
    echo "Stopping daemon and dashboard..."
    kill $(jobs -p) 2>/dev/null || true
    wait 2>/dev/null || true
    echo "Engine shut down cleanly."
}
trap cleanup EXIT INT TERM

# Start engine worker in background
echo "[1/2] Launching Engine Worker Daemon in background..."
"$PYTHON_BIN" -m src.engine_worker &
ENGINE_PID=$!

# Wait briefly to let worker initialize
sleep 2

# Start Streamlit dashboard in foreground
echo "[2/2] Launching Streamlit Dashboard..."
"$STREAMLIT_BIN" run src/dashboard.py
