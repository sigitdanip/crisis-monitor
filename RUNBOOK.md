# Crisis Monitor — Operator Runbook

Production operations guide for the Crisis Monitor backend and frontend.
Last updated: 2026-06-20

---

## 1. Quick Start

The backend runs on the VPS at `187.77.130.62:8001` and the frontend on port 3001.
Start the backend from the project root with `cd /root/crisis-monitor/backend && uv run uvicorn src.main:app --host 0.0.0.0 --port 8001`.
Start the frontend from the frontend directory with `cd /root/crisis-monitor/frontend && npm run dev -- -p 3001`.
Both services should be running at all times; the cron watchdog monitors backend health and alerts on failure.

---

## 2. Health Check

The primary health endpoint is `GET /api/system/health`, which returns a JSON object with DB status,
last pipeline run timestamp, 24-hour error and fallback counts, the current LLM model, and process uptime.
A healthy system returns `{"status": "ok", "db": "ok", ...}` with HTTP 200; any other status returns HTTP 503.
Monitor this endpoint manually with: `curl -s http://localhost:8001/api/system/health | python3 -m json.tool`.
The `/health` endpoint is a simpler liveness probe returning `{"status": "ok"}` — use it for basic uptime checks only.

---

## 3. Cron List

Both crisis-monitor cron jobs live under the `dev-lead` Hermes profile at
`/root/.hermes/profiles/dev-lead/cron/jobs.json`. They are `no_agent` scripts
(no LLM calls, minimal token cost).

- `crisis-monitor-watchdog` (id: 69cd4e6f6b8a)
  Schedule: `*/2 * * * *` (every 2 minutes)
  Deliver: `origin` (Discord DM on failure — silent on success)
  Script: `crisis_watchdog.py` at `/root/.hermes/profiles/dev-lead/scripts/`
  Workdir: `/root/.hermes/profiles/dev-lead`
  What: Probes `http://127.0.0.1:3001/api/dashboard` and `http://127.0.0.1:3001/`
  with 4s timeout. On failure, checks if backend (port 8001) or frontend (port 3001)
  listeners are missing and restarts them. 5-minute cooldown per service prevents
  restart flaps. Alerts to Discord DM only when a restart was actually attempted.

- `crisis-monitor-daily-pipeline` (id: 6f33aa192ad2)
  Schedule: `0 8 * * *` (daily at 08:00 WIB)
  Deliver: `local` (stores output locally, no push)
  Profile: `dev-lead`
  Script: `run-daily-pipeline.sh` at `/root/.hermes/profiles/dev-lead/scripts/`
  Workdir: `/root/.hermes/profiles/dev-lead`
  What: POSTs to `http://127.0.0.1:8001/api/trigger/daily` to kick off the
  full pipeline (fetchers → dot analyzers → synthesis → report). Idempotent —
  duplicate triggers within 5 minutes return the existing report.

Both jobs are verified running as of 2026-06-20. The watchdog last fired within
2 minutes; the daily pipeline last fired at 08:00 WIB today.

### 3.1 Cron Hygiene — Quarterly Audit

Cron rot (stale duplicates, missing scripts, wrong workdir, misconfigured
deliver targets) is a silent-failure risk. Run this audit quarterly or after
any Hermes profile migration:

1. **List all cron jobs across profiles:**
   - `hermes cron list` (from the dev-lead profile)
   - Or inspect the JSON files directly:
     `/root/.hermes/profiles/dev-lead/cron/jobs.json`
     `/root/.hermes/profiles/python-dev/cron/jobs.json`
     `/root/.hermes/profiles/paper-lead/cron/jobs.json`
     `/root/.hermes/cron/jobs.json`

2. **Verify the two crisis-monitor jobs are present and enabled:**
   - Both must have `"enabled": true` and `"state": "scheduled"`
   - `crisis-monitor-watchdog` must have `"deliver": "origin"`
   - `crisis-monitor-daily-pipeline` must have `"deliver": "local"`

3. **Verify last-run freshness:**
   - Watchdog `last_run_at` must be within 5 minutes (runs every 2 min)
   - Daily pipeline `last_run_at` must be within 26 hours (runs at 08:00 daily)

4. **Check for stale duplicates:**
   - No crisis-monitor jobs should exist outside the dev-lead profile
   - Look for any job with `"last_run_at": null` and a past `next_run_at`
     (never ran, broken config) — these are cron rot
   - Check that every job's `script` file actually exists at the given workdir

5. **Verify script paths:**
   - `crisis_watchdog.py` must exist at the workdir's scripts/ directory
   - `run-daily-pipeline.sh` must exist at the workdir's scripts/ directory
   - Both must be executable (`chmod +x` if needed)

6. **Repair procedure if jobs are missing or broken:**
   - If jobs are missing from dev-lead, re-create them via `hermes cron create`
     with the parameters documented above
   - If a stale duplicate exists (e.g. a dead watchdog in python-dev), remove
     the job from that profile's `jobs.json` (set `"jobs": []`)
   - After any repair, verify with `hermes cron list` and wait for the next
     scheduled tick to confirm `last_run_at` updates

---

## 4. Logs

The backend writes structured logs to `/root/crisis-monitor/backend/server.log` with timestamp, level, logger name, and message.
Each request log includes `request_id`, HTTP method, path, status code, latency in milliseconds, and user agent for tracing.
View recent logs with `tail -f /root/crisis-monitor/backend/server.log` or filter errors with `grep ERROR /root/crisis-monitor/backend/server.log`.
The 24-hour error count in the health endpoint is derived from ERROR/Traceback lines in this file.

---

## 5. Restart Procedure

To restart the backend, first kill the running process: `pkill -f "uvicorn src.main:app"` or find the PID with `ps aux | grep uvicorn`.
Wait 3 seconds for the port to release, then restart: `cd /root/crisis-monitor/backend && uv run uvicorn src.main:app --host 0.0.0.0 --port 8001 &`.
Verify the service is back with `curl -s http://localhost:8001/health` — it should return `{"status": "ok"}` within 5 seconds.
If the backend fails to start, check the server log for exceptions and verify all environment variables in `.env` are present.

---

## 6. Model Rollback

The LLM model is configured via the `LLM_MODEL` environment variable in `/root/crisis-monitor/backend/.env`.
To roll back to a previous model, edit the `.env` file and change `LLM_MODEL=mimo-v2.5` to the desired model identifier.
After changing the model, restart the backend following the Restart Procedure in Section 5.
Verify the change took effect by checking the health endpoint's `model` field: `curl -s http://localhost:8001/api/system/health | python3 -c "import sys,json; print(json.load(sys.stdin)['model'])"`.

---

## 7. Manual Re-fetch

To manually trigger a daily pipeline run, send an authenticated POST request: `curl -X POST http://localhost:8001/api/trigger/daily -H "X-Crisis-Token: <token>"`.
The token value is stored in `CRISIS_TRIGGER_TOKEN` in the backend `.env` file; you can extract it with `grep CRISIS_TRIGGER_TOKEN /root/crisis-monitor/backend/.env | cut -d= -f2`.
The trigger is idempotent — calling it twice within 5 minutes returns the existing report instead of creating a duplicate.
Monitor progress via `GET /api/pipeline/status` and view results on the dashboard at `http://187.77.130.62:3001`.

---

## 8. Browser Compatibility

The Crisis Monitor dashboard is designed for all modern browsers. This section
documents the manual cross-browser test procedure and tracks sign-offs.

### Supported Browsers

The build targets (from package.json browserslist): Chrome 111+, Edge 111+,
Firefox 111+, Safari 16+. Older or unsupported browsers may fail to load
due to missing ES module or CSS feature support.

### Manual Test Procedure

Before each production deployment, or after any frontend dependency change,
verify the dashboard renders correctly on each target browser:

1. Start the backend and frontend (see Section 1 Quick Start).
2. Open the dashboard at `http://187.77.130.62:3001` in the browser under test.
3. Verify the page loads without errors — check browser console (F12) for
   JavaScript errors or failed network requests.
4. Click the Overview tab and confirm the composite gauge renders with a
   numeric score and status indicator.
5. Click through each remaining tab (Market Monitor, Credit, Energy & Food,
   News, Pipeline) and verify content loads without blank panels or layout
   breaks.
6. On mobile (width < 768px), verify tabs scroll horizontally and panels
   stack vertically without overflow.
7. Run the automated smoke test: `bash scripts/smoke-test.sh`. All 5 checks
   must pass.

### Cross-Browser Sign-Off Matrix

Record each test run below. A deployment should not proceed without at least
Chrome, Firefox, and Safari sign-off.

| Browser | Version | Tested By | Date | Pass/Fail |
|---------|---------|-----------|------|-----------|
| Chrome  |         |           |      |           |
| Firefox |         |           |      |           |
| Edge    |         |           |      |           |
| Safari  |         |           |      |           |
| Mobile Safari (iOS) |  |     |      |           |
| Mobile Chrome (Android) |  |  |      |           |

### Smoke Test

Run `bash scripts/smoke-test.sh` to automatically verify all 5 API proxy
endpoints return HTTP 200 with valid responses. The smoke test is idempotent
and exits non-zero on failure. Run it before and after any backend restart
or frontend deployment.

---

## 9. Auth Token Rotation

The `CRISIS_TRIGGER_TOKEN` secures all trigger endpoints (daily pipeline and per-dot analysis) via the `X-Crisis-Token` header.
Rotate this token quarterly by generating a new one: `python3 -c "import secrets; print(secrets.token_urlsafe(24))"` and updating the `.env` file.
After rotation, restart the backend so the new token takes effect; any client using the old token will receive HTTP 401 responses.
Document each rotation in the team's shared password manager or secure notes; never commit `.env` files or tokens to version control.

### .env Precedence Policy

`src/main.py` calls `load_dotenv(override=True)`, meaning the `.env` file **always takes precedence** over shell environment variables.
If a var (e.g. `CRISIS_TRIGGER_TOKEN`) is set to an empty string or a stale value in the parent shell, `.env` will still win.
This prevents the `TOKEN_UNCONFIGURED` 503 lockdown that occurs when the shell has `CRISIS_TRIGGER_TOKEN=***` but `.env` has the real token.
The same policy applies to all other env vars (`OPENCODE_GO_API_KEY`, `NEWS_API_KEY`, `FRED_API_KEY`, `LLM_MODEL`).
To override an `.env` value at runtime, you must edit `.env` and restart — shell-level overrides will be ignored.
