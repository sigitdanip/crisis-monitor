#!/bin/bash
# Crisis Monitor Frontend Launcher
# Builds and starts Next.js in production mode on port 3001, bound to 0.0.0.0.
# Safe to call repeatedly: if :3001 is already in use, it exits silently.
#
# Production mode (next build + next start) eliminates Turbopack cold-start
# compile — first request is instant, no warmup loop needed, no .next/dev/lock.
#
# Race-condition protection: flock on /tmp/run-frontend.lock serializes the
# check+start sequence so two concurrent invocations can't both see the port
# as free and race to bind. Non-blocking (-n): the second launcher exits 0
# immediately instead of queueing — the watchdog cron retries every 2 min.
# The lock is kernel-managed: released on script exit (normal or SIGKILL).
#
# Used by:
#   - manual session start: `bash scripts/run-frontend.sh`
#   - paper-lead/crisis_watchdog.py cron (every 2 min)
set +m  # disable job control so the backgrounded process detaches cleanly

PORT=3001
LOG=/tmp/crisis-frontend.log
PROJECT=/root/crisis-monitor/frontend
LOCKFILE=/tmp/run-frontend.lock

# Serialize check+start under an advisory file lock to prevent TOCTOU race.
# fd 200 is opened on the lockfile; acquires an exclusive flock immediately.
# If another launcher already holds the lock, flock -n fails and we exit 0.
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "Another launcher is active (lock held on $LOCKFILE), skipping"
    exit 0
fi

# Don't double-start: if a process is already listening, kill it before rebuilding.
# Without this, the new `next build` would clobber the running server's in-memory
# chunk references — the old process serves HTML pointing at chunk hashes that
# have already been deleted by the new build, causing 500s and infinite loaders
# on the client. Kill-then-rebuild-then-start is the only safe order.
OLD_PID=$(ss -tlnp 2>/dev/null | grep ":$PORT " | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
if [ -n "$OLD_PID" ]; then
    echo "Killing old frontend server (pid $OLD_PID) before rebuild"
    kill "$OLD_PID" 2>/dev/null
    # Give it up to 5s to release the port cleanly.
    for i in 1 2 3 4 5; do
        if ! ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
            break
        fi
        sleep 1
    done
    # Force-kill if still holding the port.
    if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
        echo "Port still held after 5s, force-killing"
        kill -9 "$OLD_PID" 2>/dev/null
        sleep 1
    fi
fi

cd "$PROJECT" || exit 1

# Ensure deps are installed (idempotent, fast on second run via npm cache).
if [ ! -x node_modules/.bin/next ]; then
    echo "Installing frontend dependencies..."
    npm install --no-audit --no-fund --loglevel=error >> "$LOG" 2>&1
fi

# Production build — pre-compiles all pages so the server starts instantly.
# Subsequent builds are fast when source hasn't changed (Next.js build cache).
echo "Building frontend (production mode)..."
npx next build >> "$LOG" 2>&1
BUILD_EXIT=$?

if [ "$BUILD_EXIT" -ne 0 ]; then
    echo "Build failed (exit $BUILD_EXIT), check $LOG"
    exit 1
fi

echo "Build complete, starting production server on port $PORT..."

# nohup + & + setsid so the launcher returns immediately while next start keeps running.
nohup setsid node_modules/.bin/next start -H 0.0.0.0 -p $PORT \
    >> "$LOG" 2>&1 < /dev/null &
PID=$!
echo "PID: $PID"
disown 2>/dev/null || true

exit 0
