# Crisis Monitor V2 — System Health Baseline

This document defines what a "healthy" crisis-monitor-v2 system looks like.
Use it to diagnose regressions after future changes.

## Healthy State Definition

A healthy system has:

1. **26 active indicators** returning fresh data (recorded_at within last 24h)
2. **5 dot analyzer agents** producing real LLM synthesis (not fallback)
3. **Daily report** with confidence >= 0.85 and meaningful synthesis (>200 chars)
4. **Frontend dashboard** rendering all data correctly from backend
5. **Backend logs** clean: no ERRORs, no Tracebacks, <5 WARNINGs per 24h
6. **Cron jobs** active: crisis-monitor-daily-pipeline (last run <24h) and crisis-monitor-watchdog (last run <15min)
7. **Data sources** all returning real values (no "unavailable" in dot prompts)
8. **Production hardening**: /api/system/health reachable, auth on triggers, idempotency, no stack traces

## Indicator Baseline (Post-SHIBOR Drop)

26 indicators across 9 categories:

- Energy (5): Brent, WTI, Natural Gas, EU Gas Storage, US SPR
- Financial (5): DXY, Gold, US 10Y, US 2Y, VIX
- Credit (2): IG OAS, HY OAS
- Food (2): FAO FPI Change, CME Grains Change
- China (2): Caixin PMI, China Property Default
- Debt (2): BTP-Bund Spread, CDS Doubling
- EM Currency (3): IDR Breach, TRY Breach, EGP Breach
- Geopolitical (3): NATO Fracture, US NATO Withdrawal, Hormuz Closure
- Political (2): Govt Crisis, Protest Countries

Note: Supply Chain category has 0 active indicators (Freightos endpoint 301, no fallback).
Note: SHIBOR 1W removed — 26 indicators (was 27). BTP-Bund Spread added (Card: fred-btp-bund).
Note: News-derived indicators (Card 3) augment existing indicators with news narratives, not as separate DB rows.

## Dot Analyzer Baseline

5 agents, 10 dots:

- Agent 1 (geopolitical): dots 1 (NATO) + 2 (Energy Security)
- Agent 2 (food_debt): dots 3 (Food) + 5 (Sovereign Debt)
- Agent 3 (financial_em): dot 4 (Credit) + em_currency
- Agent 4 (china_political): dots 6 (China) + 7 (Protests) + 8 (Trade Chokepoint)
- Agent 5 (health): dot 9 (Health)

Each dot in healthy state has:
- status: dormant | activating | active | critical
- summary: 2-3 sentence LLM assessment with specific indicator values
- key_signals: list of 2-3 specific signals with numbers
- sources: paragraph citing specific indicators by name and value

## Report Baseline

- confidence: float >= 0.85
- composite_score: integer 0-16, reflects actual category scores (0 = all calm, 16 = full crisis)
- synthesis: > 200 chars, specific assessment
- five_questions: all 5 have non-empty, specific answers (>20 chars each)
- briefing: multi-paragraph narrative

## Known Pre-Existing Issues (Not Regressions)

1. **Hormuz Closure** has value=null — MarineTraffic/Kpler integration not built
2. **EU Gas Storage** (AGSI) — API requires registered key (not anonymous)
3. **US SPR** (EIA) — upstream 500 error, EIA v1 API retired
4. **Supply Chain** category has 0 indicators — Freightos endpoint 301
5. **SHIBOR** DNS resolution failure — fetcher retained but returns None
6. **FAO FPI** — both primary and fallback endpoints failing
7. **RCP Polls** — 403 Forbidden (CloudFront block)

News-derived fallbacks (Card 3) cover EU Gas/US SPR/Caixin/Protest gaps.

## Verification Command

```bash
./scripts/verify-system-health.sh [--run-slow]
```

Slow tests trigger the full pipeline (90s wait) and require CRISIS_TRIGGER_TOKEN.

## LLM Dependency

The dot analyzers require OpenCode Go API access (mimo-v2.5 model) via OPENCODE_GO_API_KEY env var.
The model name is configured via LLM_MODEL env var (default: mimo-v2.5) in backend/src/agent/llm.py.
If LLM calls time out, dots fall back to rule-based summaries. The current timeout is 25 seconds.

## Recovery Procedures

### Dots in fallback state
1. Check OPENCODE_GO_API_KEY is set in backend/.env
2. Verify OpenCode Go API is reachable: curl https://opencode.ai/zen/go/v1/models
3. Restart backend: kill uvicorn, restart with `cd backend && nohup .venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8001 &`
4. Trigger pipeline: POST /api/trigger/daily with X-Crisis-Token

### Cron jobs missing
Use `hermes cron create` to set up crisis-monitor-daily-pipeline and crisis-monitor-watchdog.

### Backend log errors
Tail server.log, identify failing fetchers, check upstream API status.
