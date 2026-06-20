#!/usr/bin/env bash
# ==========================================================================
# verify-system-health.sh
# Full system health verification for crisis-monitor v2.
#
# Runs:
#   1. Integration test (pytest)
#   2. Dashboard structure check (curl)
#   3. Log error scan (grep on server.log)
#
# Usage:
#   ./scripts/verify-system-health.sh [--run-slow]
#
# Exit: 0 if all checks pass, non-zero on first failure.
# ==========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"
LOG_FILE="$BACKEND_DIR/server.log"
BACKEND_URL="${BACKEND_URL:-http://localhost:8001}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3001}"
PASS=0
FAIL=0

red()   { echo -e "\033[31m$1\033[0m"; }
green() { echo -e "\033[32m$1\033[0m"; }
check() {
    local label="$1" result="$2" detail="$3"
    if [ "$result" = "0" ]; then
        green "  PASS: $label"
        PASS=$((PASS + 1))
    else
        red "  FAIL: $label — $detail"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Crisis Monitor System Health Verification ==="
echo "Started: $(date)"
echo "Backend: $BACKEND_URL"
echo "Frontend: $FRONTEND_URL"
echo ""

# ------------------------------------------------------------------
# 1. INTEGRATION TESTS
# ------------------------------------------------------------------
echo "--- 1. Integration Tests ---"

PYTEST_ARGS=(-v --tb=short)
if [ "${1:-}" != "--run-slow" ]; then
    PYTEST_ARGS+=(-k "not slow")
fi

cd "$BACKEND_DIR"
if .venv/bin/python3 -m pytest tests/test_system_health.py "${PYTEST_ARGS[@]}" 2>&1; then
    green "  PASS: Integration tests"
    PASS=$((PASS + 1))
else
    red "  FAIL: Integration tests"
    FAIL=$((FAIL + 1))
fi

# ------------------------------------------------------------------
# 2. DASHBOARD STRUCTURE CHECK
# ------------------------------------------------------------------
echo ""
echo "--- 2. Dashboard Structure ---"

DASH=$(curl -s --max-time 10 "$BACKEND_URL/api/dashboard" 2>/dev/null || echo "{}")

IND_COUNT=$(echo "$DASH" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('indicators',[])))" 2>/dev/null || echo 0)
check "Indicator count = 24" "$([ "$IND_COUNT" = "24" ] && echo 0 || echo 1)" "got $IND_COUNT"

DOT_COUNT=$(echo "$DASH" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('dots',[])))" 2>/dev/null || echo 0)
check "Dot count = 10" "$([ "$DOT_COUNT" = "10" ] && echo 0 || echo 1)" "got $DOT_COUNT"

PATH_COUNT=$(echo "$DASH" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('pathways',[])))" 2>/dev/null || echo 0)
check "Pathway count = 4" "$([ "$PATH_COUNT" = "4" ] && echo 0 || echo 1)" "got $PATH_COUNT"

NULL_COUNT=$(echo "$DASH" | python3 -c "
import sys,json
d=json.load(sys.stdin)
nulls=[i['name'] for i in d.get('indicators',[]) if i.get('value') is None]
print(len(nulls))
" 2>/dev/null || echo 99)
# Allow up to 3 known-null indicators (Hormuz, EU Gas, US SPR)
check "Null indicators <= 3" "$([ "$NULL_COUNT" -le 3 ] && echo 0 || echo 1)" "got $NULL_COUNT nulls"

# ------------------------------------------------------------------
# 3. LOG ERROR SCAN
# ------------------------------------------------------------------
echo ""
echo "--- 3. Log Error Scan ---"

if [ ! -f "$LOG_FILE" ]; then
    red "  FAIL: Log file not found: $LOG_FILE"
    FAIL=$((FAIL + 1))
else
    ERROR_COUNT=$(grep -c "ERROR" "$LOG_FILE" 2>/dev/null || echo 0)
    TRACEBACK_COUNT=$(grep -c "Traceback" "$LOG_FILE" 2>/dev/null || echo 0)
    WARNING_COUNT=$(grep -c "WARNING" "$LOG_FILE" 2>/dev/null || echo 0)

    # Only count recent entries (last 24h heuristic: last 1000 lines)
    RECENT=$(tail -1000 "$LOG_FILE")
    RECENT_ERRORS=$(echo "$RECENT" | grep -c "ERROR" || echo 0)
    RECENT_TRACEBACKS=$(echo "$RECENT" | grep -c "Traceback" || echo 0)
    RECENT_WARNINGS=$(echo "$RECENT" | grep -c "WARNING" || echo 0)

    echo "  Total lines: $(wc -l < "$LOG_FILE")"
    echo "  Recent ERRORs: $RECENT_ERRORS"
    echo "  Recent Tracebacks: $RECENT_TRACEBACKS"
    echo "  Recent WARNINGs: $RECENT_WARNINGS"

    check "No ERRORs in recent log" "$([ "$RECENT_ERRORS" = "0" ] && echo 0 || echo 1)" "got $RECENT_ERRORS"
    check "No Tracebacks in recent log" "$([ "$RECENT_TRACEBACKS" = "0" ] && echo 0 || echo 1)" "got $RECENT_TRACEBACKS"
    check "WARNINGs < 5 in recent log" "$([ "$RECENT_WARNINGS" -lt 5 ] && echo 0 || echo 1)" "got $RECENT_WARNINGS"
fi

# ------------------------------------------------------------------
# SUMMARY
# ------------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"

if [ "$FAIL" -gt 0 ]; then
    red "VERIFICATION FAILED — $FAIL check(s) did not pass"
    exit 1
else
    green "VERIFICATION PASSED — system is healthy"
    exit 0
fi
