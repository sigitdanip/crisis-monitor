#!/bin/bash
# Crisis Monitor Daily Pipeline Trigger
# POSTs to /api/trigger/daily on the local backend. Logs result + any error.
# Idempotent: if the backend is down, logs the failure and exits non-zero so
# the parent cron (or you, running it manually) sees something went wrong.
#
# Used by:
#   - manual run:        bash scripts/run-daily-pipeline.sh
#   - cron (dev-lead):   0 8 * * *  -> run-daily-pipeline.sh
#
# Note: The endpoint now returns 202 Accepted immediately (pipeline runs
# as a background task). The script exits 0 on 200 or 202.
set -u

URL="http://127.0.0.1:8001/api/trigger/daily"
LOG="/tmp/crisis-daily-pipeline.log"
TS() { date '+%Y-%m-%d %H:%M:%S %Z'; }

echo "=== $(TS) === trigger-daily starting" >> "$LOG"

# Sanity: is the backend up?
if ! ss -tlnp 2>/dev/null | grep -q ':8001 '; then
    echo "  backend port 8001 not listening, skipping (watchdog will retry)" >> "$LOG"
    exit 0
fi

# Hit the endpoint. 120s timeout — pipeline runs in background now,
# so the endpoint returns in <1s. The 120s is a generous ceiling for
# edge cases where the backend is slow to accept the connection.
RESP=$(curl -sS -m 120 -X POST -w "\nHTTP_CODE:%{http_code}\nTIME:%{time_total}\n" "$URL" 2>&1)
RC=$?

if [ $RC -ne 0 ]; then
    echo "  curl failed (exit $RC): $RESP" >> "$LOG"
    exit 1
fi

HTTP=$(echo "$RESP" | grep '^HTTP_CODE:' | cut -d: -f2)
echo "  http=$HTTP  time=$(echo "$RESP" | grep '^TIME:' | cut -d: -f2)s" >> "$LOG"
echo "  body: $(echo "$RESP" | grep -v '^HTTP_CODE:\|^TIME:')" >> "$LOG"

if [ "$HTTP" != "200" ] && [ "$HTTP" != "202" ]; then
    exit 1
fi
exit 0
