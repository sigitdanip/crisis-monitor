#!/bin/bash
# Crisis Monitor Backend Launcher
# Starts FastAPI backend (uvicorn) on port 8001, detached.
# Safe to call repeatedly: if :8001 is already in use, it exits silently.
#
# Used by:
#   - manual session start: `bash scripts/run-backend.sh`
#   - paper-lead/crisis_watchdog.py cron (every 2 min)
set +m  # disable job control so the backgrounded process detaches cleanly

PORT=8001
LOG=/tmp/crisis-backend.log
PROJECT=/root/crisis-monitor/backend

# Don't double-start: if a process is already listening, bail.
if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
    echo "Port $PORT already in use, skipping backend start"
    exit 0
fi

cd "$PROJECT" || exit 1

# Ensure venv exists (idempotent — reuses existing venv if present).
if [ ! -x .venv/bin/uvicorn ]; then
    echo "Creating backend venv..."
    python3.11 -m venv .venv
    .venv/bin/pip install -q -e . 2>>"$LOG" || exit 1
fi

# nohup + & so the launcher returns immediately while uvicorn keeps running.
# `setsid` puts uvicorn in its own session so it survives the parent shell.
nohup setsid .venv/bin/uvicorn src.main:app --host 0.0.0.0 --port $PORT \
    >> "$LOG" 2>&1 < /dev/null &
PID=$!
echo "PID: $PID"
disown 2>/dev/null || true
exit 0
