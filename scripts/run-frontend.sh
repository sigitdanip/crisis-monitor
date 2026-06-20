#!/bin/bash
# Crisis Monitor Frontend Launcher
# Starts Next.js dev server on port 3001, bound to 0.0.0.0.
# Safe to call repeatedly: if :3001 is already in use, it exits silently.
#
# Used by:
#   - manual session start: `bash scripts/run-frontend.sh`
#   - paper-lead/crisis_watchdog.py cron (every 2 min)
set +m  # disable job control so the backgrounded process detaches cleanly

PORT=3001
LOG=/tmp/crisis-frontend.log
PROJECT=/root/crisis-monitor/frontend

# Don't double-start: if a process is already listening, bail.
if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
    echo "Port $PORT already in use, skipping frontend start"
    exit 0
fi

cd "$PROJECT" || exit 1

# Ensure deps are installed (idempotent, fast on second run via npm cache).
if [ ! -x node_modules/.bin/next ]; then
    echo "Installing frontend dependencies..."
    npm install --no-audit --no-fund --loglevel=error >> "$LOG" 2>&1
fi

# nohup + & + setsid so the launcher returns immediately while next dev keeps running.
nohup setsid node_modules/.bin/next dev -H 0.0.0.0 -p $PORT \
    >> "$LOG" 2>&1 < /dev/null &
PID=$!
echo "PID: $PID"
disown 2>/dev/null || true
exit 0
