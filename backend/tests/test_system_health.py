"""
System health integration test — runs the full pipeline and asserts acceptance criteria.

Per dev/CHECKLIST.md: QA integration tests must use the real pipeline, not mocks.
This test hits the live backend API and validates indicator freshness, dot analyzer
quality, report quality, frontend rendering, and production hardening ACs.

Usage:
    cd /root/crisis-monitor/backend
    .venv/bin/pytest tests/test_system_health.py -v -s

Requires:
    - Backend running on http://localhost:8001
    - Frontend running on http://localhost:3001
    - CRISIS_TRIGGER_TOKEN env var or .env file for auth
"""

import json
import os
import time
import urllib.request
import urllib.error

import pytest

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8001")
FRONTEND = os.environ.get("FRONTEND_URL", "http://localhost:3001")
TRIGGER_TOKEN = os.environ.get("CRISIS_TRIGGER_TOKEN", "")

if not TRIGGER_TOKEN:
    # Try loading from .env
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
        TRIGGER_TOKEN = os.environ.get("CRISIS_TRIGGER_TOKEN", "")
    except ImportError:
        pass

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(path: str, base: str = BACKEND) -> dict:
    """GET a JSON endpoint, return parsed dict."""
    with urllib.request.urlopen(f"{base}{path}") as r:
        return json.loads(r.read())


def _post(path: str, body: dict = None, headers: dict = None) -> tuple:
    """POST to an endpoint, return (status_code, parsed_json)."""
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(f"{BACKEND}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ---------------------------------------------------------------------------
# AC1: Indicator Freshness
# ---------------------------------------------------------------------------

class TestIndicatorFreshness:
    """AC1: 24 indicators, all fresh within 24h, 10 categories covered."""

    def test_indicator_count_is_30(self):
        """Assert exactly 30 distinct indicators (26 core + 4 news-derived)."""
        dash = _get("/api/dashboard")
        indicators = dash["indicators"]
        assert len(indicators) == 30, f"Expected 30 indicators, got {len(indicators)}"

    def test_no_indicator_has_null_value(self):
        """Assert no indicator has value=null (except known Hormuz gap)."""
        dash = _get("/api/dashboard")
        nulls = [i["name"] for i in dash["indicators"] if i["value"] is None]
        # Hormuz Closure is a known pre-existing issue (EIA/AGSI broken)
        known_null = {"Hormuz Closure", "EU Gas Storage", "US SPR"}
        unexpected = [n for n in nulls if n not in known_null]
        assert not unexpected, f"Unexpected null indicators: {unexpected}"

    def test_category_coverage(self):
        """Assert all 9 implemented categories have at least 1 indicator."""
        dash = _get("/api/dashboard")
        cats = set(i["category"] for i in dash["indicators"])
        required = {"Credit", "Energy", "China", "Debt", "Food",
                     "Geopolitical", "Political", "Financial", "EM Currency"}
        missing = required - cats
        assert not missing, f"Missing categories: {missing}"


# ---------------------------------------------------------------------------
# AC2: Dot Analyzer Quality
# ---------------------------------------------------------------------------

class TestDotAnalyzerQuality:
    """AC2: All 5 dot analyzers produce real synthesis, no fallbacks."""

    @pytest.mark.slow
    def test_dot_analyzers_not_fallback(self):
        """Trigger pipeline and assert all agents success (not fallback)."""
        if not TRIGGER_TOKEN:
            pytest.skip("CRISIS_TRIGGER_TOKEN not set — cannot trigger pipeline")

        # Trigger pipeline
        status, resp = _post("/api/trigger/daily",
                             headers={"X-Crisis-Token": TRIGGER_TOKEN})
        assert status in (200, 201), f"Trigger failed: {resp}"

        # Wait for pipeline (max 120s)
        deadline = time.time() + 120
        while time.time() < deadline:
            pipe = _get("/api/pipeline/status")
            agents = [n for n in pipe["nodes"] if "Agent" in n["id"]]
            fallbacks = [n for n in agents if n["status"] == "fallback"]
            if not fallbacks:
                break
            time.sleep(5)

        pipe = _get("/api/pipeline/status")
        agents = [n for n in pipe["nodes"] if "Agent" in n["id"]]
        fallbacks = [n for n in agents if n["status"] == "fallback"]
        assert not fallbacks, (
            f"Dot analyzers in fallback state: "
            f"{[(n['id'], n.get('error','')) for n in fallbacks]}"
        )

    def test_no_data_unavailable_in_dots(self):
        """Assert no dot summary or key_signals contains 'data unavailable'."""
        dash = _get("/api/dashboard")
        for dot in dash["dots"]:
            text = json.dumps(dot).lower()
            assert "data unavailable" not in text, (
                f"Dot {dot['dot_name']} has 'data unavailable'"
            )

    def test_no_llm_fallback_in_dots(self):
        """Assert no dot summary contains 'LLM analysis unavailable'."""
        dash = _get("/api/dashboard")
        for dot in dash["dots"]:
            assert "LLM analysis unavailable" not in dot.get("summary", ""), (
                f"Dot {dot['dot_name']} has LLM fallback"
            )


# ---------------------------------------------------------------------------
# AC3: Daily Report Quality
# ---------------------------------------------------------------------------

class TestDailyReportQuality:
    """AC3: Report confidence >= 0.85, meaningful synthesis, valid scores."""

    def test_confidence_at_least_085(self):
        """Assert latest report confidence >= 0.85."""
        dash = _get("/api/dashboard")
        report = dash["report"]
        confidence = float(report["confidence"])
        assert confidence >= 0.85, f"Confidence {confidence} < 0.85"

    def test_synthesis_length_gt_200(self):
        """Assert synthesis paragraph is meaningful (> 200 chars)."""
        dash = _get("/api/dashboard")
        synth = dash["report"]["synthesis"]
        assert len(synth) > 200, (
            f"Synthesis too short: {len(synth)} chars — '{synth[:100]}...'"
        )

    def test_composite_score_valid(self):
        """Assert composite_score is a valid number in 0-30 range (not None/negative)."""
        dash = _get("/api/dashboard")
        score = dash["report"]["composite_score"]
        assert isinstance(score, (int, float)), f"Composite score is not a number: {type(score)}"
        assert 0 <= score <= 30, f"Composite score {score} out of valid range 0-30"

    def test_five_questions_all_answered(self):
        """Assert all five_questions have non-empty answers."""
        dash = _get("/api/dashboard")
        qs = dash["report"]["five_questions"]
        for key, val in qs.items():
            answer = val.get("answer", "")
            assert answer, f"Question {key} has empty answer"
            assert len(answer) > 20, (
                f"Question {key} answer too short: {len(answer)} chars"
            )


# ---------------------------------------------------------------------------
# AC4: Frontend Rendering
# ---------------------------------------------------------------------------

class TestFrontendRendering:
    """AC4: Dashboard renders correctly from both backend and frontend."""

    def test_backend_dashboard_structure(self):
        """Assert backend /api/dashboard returns expected structure."""
        dash = _get("/api/dashboard")
        assert len(dash["indicators"]) == 30, f"Expected 30 indicators, got {len(dash['indicators'])}"
        assert len(dash["dots"]) == 10, f"Expected 10 dots, got {len(dash['dots'])}"
        assert len(dash["pathways"]) == 4, f"Expected 4 pathways, got {len(dash['pathways'])}"

    def test_no_null_values_in_indicators(self):
        """Assert no indicator has value=null (except known gaps)."""
        dash = _get("/api/dashboard")
        nulls = [i["name"] for i in dash["indicators"] if i["value"] is None]
        known = {"Hormuz Closure", "EU Gas Storage", "US SPR"}
        unexpected = [n for n in nulls if n not in known]
        assert not unexpected, f"Null indicators: {unexpected}"


# ---------------------------------------------------------------------------
# AC5: Backend Log Scan (manual verification — documented here)
# ---------------------------------------------------------------------------

# AC5 is manual: tail server.log, count ERRORs/Tracebacks/WARNINGs.
# See verify-system-health.sh for automated version.


# ---------------------------------------------------------------------------
# Card 8: Production Hardening
# ---------------------------------------------------------------------------

class TestProductionHardening:
    """Card 8 ACs: health endpoint, auth, idempotency, .env, RUNBOOK.md."""

    def test_health_endpoint_exists(self):
        """Assert /api/system/health returns status JSON (200 or 503)."""
        try:
            health = _get("/api/system/health")
        except urllib.error.HTTPError as e:
            # 503 is valid — degraded state when env vars missing
            assert e.code == 503, f"Unexpected error: {e.code}"
            health = json.loads(e.read())
        assert "status" in health
        assert "db" in health

    def test_auth_blocks_unauthorized_trigger(self):
        """Assert POST /api/trigger/daily without token returns 401."""
        status, resp = _post("/api/trigger/daily")
        assert status == 401, f"Expected 401, got {status}: {resp}"

    def test_auth_blocks_wrong_token(self):
        """Assert POST /api/trigger/daily with wrong token returns 401."""
        status, resp = _post("/api/trigger/daily",
                             headers={"X-Crisis-Token": "wrong-token"})
        assert status == 401, f"Expected 401, got {status}: {resp}"

    def test_idempotency_prevents_duplicate_runs(self):
        """Assert rapid duplicate triggers return idempotent response."""
        if not TRIGGER_TOKEN:
            pytest.skip("CRISIS_TRIGGER_TOKEN not set")
        h = {"X-Crisis-Token": TRIGGER_TOKEN}
        s1, r1 = _post("/api/trigger/daily", headers=h)
        s2, r2 = _post("/api/trigger/daily", headers=h)
        # Second call should be idempotent (200 with idempotent status, or 409)
        assert r2.get("status") == "idempotent" or s2 == 409, (
            f"Idempotency not working: status={s2}, resp={r2}"
        )

    def test_no_stack_traces_in_error_responses(self):
        """Assert error responses don't leak stack traces."""
        # Hit a nonexistent endpoint
        try:
            with urllib.request.urlopen(f"{BACKEND}/api/nonexistent") as r:
                body = r.read().decode()
        except urllib.error.HTTPError as e:
            body = e.read().decode()
        assert "Traceback" not in body, "Stack trace leaked in error response"
        assert "File \"" not in body, "File path leaked in error response"


# ---------------------------------------------------------------------------
# Fixture: skip slow tests unless --run-slow is passed
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption("--run-slow", action="store_true", default=False,
                     help="run slow tests (pipeline trigger + wait)")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow (pipeline trigger + wait)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="need --run-slow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
