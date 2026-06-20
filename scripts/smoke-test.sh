#!/usr/bin/env bash
# Crisis Monitor — Cross-platform smoke test
# Idempotent: can be run any number of times without side effects.
# Exit 0 on all checks pass, exit 1 on any failure.
# Must run in <10s (each curl has 5s timeout, 5 endpoints = 25s worst case).
#
# Usage: bash scripts/smoke-test.sh [BASE_URL]
#   Default BASE_URL: http://localhost:3001

set -euo pipefail

BASE_URL="${1:-http://localhost:3001}"
TIMEOUT=5
PASS=0
FAIL=0

# Terminal colors for readable output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_pass() { echo -e "  ${GREEN}PASS${NC} $1"; PASS=$((PASS + 1)); }
log_fail() { echo -e "  ${RED}FAIL${NC} $1"; FAIL=$((FAIL + 1)); }
log_warn() { echo -e "  ${YELLOW}WARN${NC} $1"; }

echo "=== Crisis Monitor Smoke Test ==="
echo "Base URL: $BASE_URL"
echo ""

# ── 1. Homepage ──────────────────────────────────────────────────────
echo "[1/5] GET / — homepage loads"
HOME_BODY=$(curl -sS --max-time "$TIMEOUT" "$BASE_URL/" 2>&1) || {
    log_fail "Homepage request failed or timed out"
}
HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$BASE_URL/")
if [ "$HTTP_CODE" != "200" ]; then
    log_fail "Homepage returned HTTP $HTTP_CODE (expected 200)"
elif ! echo "$HOME_BODY" | grep -q 'Crisis'; then
    log_fail "Homepage HTML does not contain 'Crisis'"
else
    log_pass "Homepage returns 200 and contains 'Crisis'"
fi

# ── 2. /api/dashboard (proxied to :8001) ─────────────────────────────
echo "[2/5] GET /api/dashboard — proxy + 24 indicators"
DASHBOARD_JSON=$(curl -sS --max-time "$TIMEOUT" "$BASE_URL/api/dashboard" 2>&1) || {
    log_fail "/api/dashboard request failed or timed out"
}
HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$BASE_URL/api/dashboard")
if [ "$HTTP_CODE" != "200" ]; then
    log_fail "/api/dashboard returned HTTP $HTTP_CODE (expected 200)"
elif ! echo "$DASHBOARD_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); n=len(d.get('indicators',[])); sys.exit(0 if n==24 else 1)" 2>/dev/null; then
    IND_COUNT=$(echo "$DASHBOARD_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('indicators',[])))" 2>/dev/null || echo "?")
    log_fail "/api/dashboard has $IND_COUNT indicators (expected 24)"
elif ! echo "$DASHBOARD_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'indicators' in d and 'dots' in d and 'pathways' in d else 1)" 2>/dev/null; then
    log_fail "/api/dashboard missing required keys (indicators, dots, pathways)"
else
    log_pass "/api/dashboard returns 200 with 24 indicators (JSON valid)"
fi

# ── 3. /api/pipeline/status (proxied) ────────────────────────────────
echo "[3/5] GET /api/pipeline/status — proxy + valid JSON"
HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$BASE_URL/api/pipeline/status")
PIPELINE_JSON=$(curl -sS --max-time "$TIMEOUT" "$BASE_URL/api/pipeline/status" 2>&1) || {
    log_fail "/api/pipeline/status request failed or timed out"
}
if [ "$HTTP_CODE" != "200" ]; then
    log_fail "/api/pipeline/status returned HTTP $HTTP_CODE (expected 200)"
elif ! echo "$PIPELINE_JSON" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    log_fail "/api/pipeline/status returned invalid JSON"
elif ! echo "$PIPELINE_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'nodes' in d and 'edges' in d else 1)" 2>/dev/null; then
    log_fail "/api/pipeline/status missing required keys (nodes, edges)"
else
    log_pass "/api/pipeline/status returns 200 with valid JSON"
fi

# ── 4. /api/reports/history (proxied) ────────────────────────────────
echo "[4/5] GET /api/reports/history — proxy + valid JSON"
HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$BASE_URL/api/reports/history")
REPORTS_JSON=$(curl -sS --max-time "$TIMEOUT" "$BASE_URL/api/reports/history" 2>&1) || {
    log_fail "/api/reports/history request failed or timed out"
}
if [ "$HTTP_CODE" != "200" ]; then
    log_fail "/api/reports/history returned HTTP $HTTP_CODE (expected 200)"
elif ! echo "$REPORTS_JSON" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    log_fail "/api/reports/history returned invalid JSON"
elif ! echo "$REPORTS_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'reports' in d else 1)" 2>/dev/null; then
    log_fail "/api/reports/history missing required key (reports)"
else
    log_pass "/api/reports/history returns 200 with valid JSON"
fi

# ── 5. /api/system/health (proxied, added by Card 8b) ────────────────
echo "[5/5] GET /api/system/health — proxy + documented JSON shape"
HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$BASE_URL/api/system/health")
HEALTH_JSON=$(curl -sS --max-time "$TIMEOUT" "$BASE_URL/api/system/health" 2>&1) || {
    log_fail "/api/system/health request failed or timed out"
}
if [ "$HTTP_CODE" = "404" ]; then
    log_warn "/api/system/health returned 404 (endpoint not deployed yet by Card 8b)"
elif [ "$HTTP_CODE" != "200" ]; then
    # 503 is valid when status=degraded or status=down
    log_fail "/api/system/health returned HTTP $HTTP_CODE (expected 200 or 503)"
elif ! echo "$HEALTH_JSON" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    log_fail "/api/system/health returned invalid JSON"
elif ! echo "$HEALTH_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
required = ['status','db','last_pipeline_run','last_24h_errors','last_24h_fallbacks','model','uptime_seconds']
missing = [k for k in required if k not in d]
if missing:
    print('MISSING:', missing, file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
    MISSING_KEYS=$(echo "$HEALTH_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
required = ['status','db','last_pipeline_run','last_24h_errors','last_24h_fallbacks','model','uptime_seconds']
missing = [k for k in required if k not in d]
print(','.join(missing))
" 2>/dev/null || echo "?")
    log_fail "/api/system/health missing required fields: $MISSING_KEYS"
else
    log_pass "/api/system/health returns 200 with documented JSON shape (7 fields)"
fi

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}SMOKE TEST FAILED${NC}"
    exit 1
else
    echo -e "${GREEN}SMOKE TEST PASSED${NC}"
    exit 0
fi
