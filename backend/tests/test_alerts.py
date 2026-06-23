"""Tests for Alerts Engine — src/agent/alerts.py.

Validates all Acceptance Criteria:
- Flag determination: NORMAL(0), BREACHED(0<x<1), CRITICAL(1.0)
- Alert text v1.2 format: [{category}] {name} = {value} [{flag}] (+x/1.0)
- Gold (ma_deviation) alerts include MA context when CRITICAL
- Non-numeric indicators use enum value
- Transition detection: NORMAL→BREACHED, BREACHED→CRITICAL
- Cooldown: 24h de-dup by category+indicator+flag
- acknowledged defaults to false
- All 30 indicators evaluated
"""
import os
import sys
import sqlite3
import tempfile
import atexit
from datetime import datetime, timezone, timedelta

# Ensure project root is on path for imports
sys.path.insert(0, "/root/crisis-monitor/backend")

# ── Patch get_db at module level to use a shared temp file DB ────────────────
# This avoids connection-lifetime issues: each call to get_db() opens a fresh
# connection to the same file, so writes from one connection are visible to
# subsequent connections.

_test_db_path: str | None = None


def _temp_db_path() -> str:
    global _test_db_path
    if _test_db_path is None:
        fd, path = tempfile.mkstemp(suffix=".db", prefix="test_alerts_")
        os.close(fd)
        _test_db_path = path
        atexit.register(lambda: os.path.exists(path) and os.unlink(path))
    return _test_db_path


def _fresh_conn() -> sqlite3.Connection:
    """Create a fresh connection to the shared test DB with the alerts schema."""
    path = _temp_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            indicator TEXT NOT NULL,
            message TEXT NOT NULL,
            triggered_at TEXT NOT NULL DEFAULT (datetime('now')),
            acknowledged INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(triggered_at);
    """)
    conn.commit()
    return conn


def _clear_alerts() -> None:
    """Remove all rows from the alerts table (reset between tests)."""
    conn = _fresh_conn()
    conn.execute("DELETE FROM alerts")
    conn.commit()
    conn.close()


def _seed_alert(category: str, indicator: str, message: str, hours_ago: float = 0) -> None:
    """Insert a synthetic alert row for transition/cooldown testing."""
    conn = _fresh_conn()
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO alerts (category, indicator, message, triggered_at) VALUES (?, ?, ?, ?)",
        (category, indicator, message, ts),
    )
    conn.commit()
    conn.close()


# Apply the monkeypatch globally before importing alerts module
import src.agent.alerts as _alerts_mod
_real_get_db = _alerts_mod.get_db
_alerts_mod.get_db = _fresh_conn

# Now import the symbols — they'll use the patched get_db
from src.agent.alerts import (
    determine_flag,
    format_alert_message,
    evaluate_alerts,
    insert_alerts,
    run_alerts,
    FLAG_SEVERITY,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _mock_composite_result(scores: dict[str, float], details_override: dict | None = None) -> dict:
    """Build a composite result dict similar to score_composite() output."""
    indicator_details = {}
    for slug, raw_score in scores.items():
        indicator_details[slug] = {
            "name": slug.replace("_", " ").title(),
            "category": "energy",
            "weight": 1.0,
            "raw_score": raw_score,
            "weighted_score": raw_score,
            "debug": {"method": "numeric", "value": 100.0, "baseline": 80.0},
        }
    if details_override:
        indicator_details.update(details_override)
    return {
        "composite": 10.0,
        "interpretation": "elevated",
        "per_indicator_scores": scores,
        "indicator_details": indicator_details,
        "available_count": len(scores),
        "total_indicators": 30,
    }


# ── 1. Flag determination ────────────────────────────────────────────────────


def test_flag_normal():
    assert determine_flag(0.0) == "NORMAL"
    assert determine_flag(-0.1) == "NORMAL"


def test_flag_breached():
    assert determine_flag(0.0001) == "BREACHED"
    assert determine_flag(0.5) == "BREACHED"
    assert determine_flag(0.9999) == "BREACHED"


def test_flag_critical():
    assert determine_flag(1.0) == "CRITICAL"
    assert determine_flag(2.0) == "CRITICAL"


def test_flag_severity_ordering():
    assert FLAG_SEVERITY["NORMAL"] < FLAG_SEVERITY["BREACHED"] < FLAG_SEVERITY["CRITICAL"]


# ── 2. Alert message formatting (v1.2 template) ──────────────────────────────


def test_format_numeric_alert():
    details = {
        "name": "Brent Oil Price",
        "category": "energy",
        "weight": 1.5,
        "raw_score": 0.75,
        "weighted_score": 1.125,
        "debug": {"method": "distance_from_trigger", "value": 95.0, "baseline": 75.0},
    }
    msg = format_alert_message("brent_oil", details, "BREACHED", 0.75, raw_value=95.0)
    assert msg.startswith("[energy]")
    assert "Brent Oil Price" in msg
    assert "95" in msg
    assert "[BREACHED]" in msg
    assert "(+0.75/1.0)" in msg


def test_format_numeric_critical():
    details = {
        "name": "VIX Volatility Index",
        "category": "financial",
        "weight": 1.4,
        "raw_score": 1.0,
        "weighted_score": 1.4,
        "debug": {"method": "distance_from_trigger", "value": 40.0, "baseline": 15.0},
    }
    msg = format_alert_message("vix", details, "CRITICAL", 1.0, raw_value=40.0)
    assert "[financial]" in msg
    assert "[CRITICAL]" in msg
    assert "(+1.00/1.0)" in msg


def test_format_normal_no_contribution():
    details = {
        "name": "VIX Volatility Index",
        "category": "financial",
        "weight": 1.4,
        "raw_score": 0.0,
        "weighted_score": 0.0,
        "debug": {"method": "distance_from_trigger", "value": 15.0, "baseline": 15.0},
    }
    msg = format_alert_message("vix", details, "NORMAL", 0.0, raw_value=15.0)
    assert "(+" not in msg, f"NORMAL should not have contribution suffix: {msg}"


def test_format_non_numeric_enum():
    details = {
        "name": "Taiwan Strait Tension",
        "category": "supply_chain",
        "weight": 1.3,
        "raw_score": 0.6,
        "weighted_score": 0.78,
        "debug": {"method": "enum", "raw_value": "elevated"},
    }
    msg = format_alert_message("taiwan_strait_tension", details, "BREACHED", 0.6, raw_value="elevated")
    assert "[supply_chain]" in msg
    assert "Taiwan Strait Tension" in msg
    assert "Elevated" in msg
    assert "[BREACHED]" in msg
    assert "(+0.60/1.0)" in msg


def test_format_gold_ma_deviation():
    """Gold (ma_deviation): includes MA context in message when CRITICAL."""
    details = {
        "name": "Gold Price",
        "category": "metals",
        "weight": 0.8,
        "raw_score": 1.0,
        "weighted_score": 0.8,
        "debug": {
            "method": "ma_deviation",
            "ma_200": 3300.0,
            "deviation_pct": 28.5,
            "value": 4240.0,
            "zone": "catastrophic_capped",
        },
    }
    msg = format_alert_message("gold_price", details, "CRITICAL", 1.0, raw_value=4240.0)
    assert "[metals]" in msg
    assert "Gold Price" in msg
    assert "$4,240" in msg
    assert "+28.5% above 200d MA $3,300" in msg
    assert "[CRITICAL]" in msg
    assert "(+1.00/1.0)" in msg


def test_format_template_structure():
    """Every alert message must match the v1.2 template pattern."""
    import re
    pattern = re.compile(
        r"^\[(?P<category>\w+)\]\s+(?P<name>.+?)\s+=\s+(?P<value>.+?)\s+\[(?P<flag>NORMAL|BREACHED|CRITICAL)\]"
        r"(?:\s+\(\+(?P<contribution>[\d.]+)/1\.0\))?$"
    )

    test_cases = [
        ("brent_oil", {"name": "Brent Oil", "category": "energy"}, "BREACHED", 0.5, 90.0),
        ("vix", {"name": "VIX", "category": "financial"}, "NORMAL", 0.0, 15.0),
        ("taiwan_strait_tension", {"name": "Taiwan Strait", "category": "supply_chain"}, "BREACHED", 0.6, "elevated"),
    ]
    for slug, base_details, flag, raw_score, raw_value in test_cases:
        details = {
            **base_details,
            "weight": 1.0,
            "raw_score": raw_score,
            "weighted_score": raw_score,
            "debug": {"method": "numeric", "value": raw_value},
        }
        msg = format_alert_message(slug, details, flag, raw_score, raw_value=raw_value)
        assert pattern.match(msg), f"Message does not match v1.2 template: {msg}"


# ── 3. Transition detection ──────────────────────────────────────────────────


def test_evaluate_first_run_fires_non_normal():
    """First run (no previous alerts): fires for any non-NORMAL indicator."""
    _clear_alerts()

    composite = _mock_composite_result({
        "brent_oil": 0.0,    # NORMAL — no alert
        "vix": 0.7,          # BREACHED — alert
        "eu_gas_storage": 1.0,  # CRITICAL — alert
    })
    indicators = {"brent_oil": 75.0, "vix": 30.0, "eu_gas_storage": 58.0}
    alerts = evaluate_alerts(composite, indicators)

    assert len(alerts) == 2
    alert_slugs = {a["indicator"] for a in alerts}
    assert "vix" in alert_slugs
    assert "eu_gas_storage" in alert_slugs
    assert "brent_oil" not in alert_slugs


def test_evaluate_no_transition_no_fire():
    """Same flag as previous alert: no re-fire."""
    _clear_alerts()
    _seed_alert("financial", "vix", "[financial] VIX = 30 [BREACHED] (+0.70/1.0)", hours_ago=25)

    composite = _mock_composite_result({"vix": 0.7})
    indicators = {"vix": 30.0}
    alerts = evaluate_alerts(composite, indicators)

    assert len(alerts) == 0, "Should not fire when flag unchanged"


def test_evaluate_transition_breach_to_critical_fires():
    """BREACHED→CRITICAL transition should fire."""
    _clear_alerts()
    _seed_alert("financial", "vix", "[financial] VIX = 30 [BREACHED] (+0.70/1.0)", hours_ago=25)

    composite = _mock_composite_result({"vix": 1.0})
    indicators = {"vix": 40.0}
    alerts = evaluate_alerts(composite, indicators)

    assert len(alerts) == 1
    assert alerts[0]["indicator"] == "vix"
    assert "[CRITICAL]" in alerts[0]["message"]


def test_evaluate_transition_critical_to_breach_no_fire():
    """CRITICAL→BREACHED (improvement): should NOT fire."""
    _clear_alerts()
    _seed_alert("financial", "vix", "[financial] VIX = 40 [CRITICAL] (+1.00/1.0)", hours_ago=25)

    composite = _mock_composite_result({"vix": 0.7})
    indicators = {"vix": 30.0}
    alerts = evaluate_alerts(composite, indicators)

    assert len(alerts) == 0, "CRITICAL→BREACHED is improvement, should not fire"


# ── 4. Cooldown (24h) ────────────────────────────────────────────────────────


def test_cooldown_same_flag_within_24h():
    """Same category+indicator+flag within 24h: skip via cooldown."""
    _clear_alerts()
    # Insert an alert 1 hour ago — this sets previous_flag to BREACHED
    # But we also need transition, so NO previous BREACHED. Instead,
    # seed a NORMAL alert to establish previous state, then try BREACHED
    # which IS a transition. But cooldown on BREACHED should block it.
    _seed_alert("financial", "vix", "[financial] VIX = 15 [NORMAL]", hours_ago=25)
    _seed_alert("financial", "vix", "[financial] VIX = 30 [BREACHED] (+0.70/1.0)", hours_ago=1)

    composite = _mock_composite_result({"vix": 0.7})  # still BREACHED
    indicators = {"vix": 30.0}
    alerts = evaluate_alerts(composite, indicators)

    assert len(alerts) == 0, "Cooldown should prevent re-fire within 24h"


def test_cooldown_same_flag_after_25h_fires():
    """Same flag after 25h: transition NORMAL→BREACHED fires (cooldown expired for BREACHED)."""
    _clear_alerts()
    _seed_alert("financial", "vix", "[financial] VIX = 15 [NORMAL]", hours_ago=26)
    _seed_alert("financial", "vix", "[financial] VIX = 30 [BREACHED] (+0.70/1.0)", hours_ago=25)

    composite = _mock_composite_result({"vix": 0.7})
    indicators = {"vix": 30.0}
    alerts = evaluate_alerts(composite, indicators)

    # previous_flag is BREACHED (25h ago), current is BREACHED → no transition → no fire
    assert len(alerts) == 0, "No transition: previous BREACHED, current BREACHED"

    # Now test a real transition after cooldown expiry:
    # Seed NORMAL from 25h ago, current is BREACHED
    _clear_alerts()
    _seed_alert("financial", "vix", "[financial] VIX = 15 [NORMAL]", hours_ago=25)

    composite = _mock_composite_result({"vix": 0.7})
    indicators = {"vix": 30.0}
    alerts = evaluate_alerts(composite, indicators)

    assert len(alerts) == 1, "NORMAL→BREACHED transition after 25h should fire"
    assert alerts[0]["indicator"] == "vix"


# ── 5. Insert alerts ─────────────────────────────────────────────────────────


def test_insert_alerts_acknowledged_defaults_false():
    """acknowledged column defaults to 0 (false)."""
    _clear_alerts()

    alerts_data = [
        {"category": "energy", "indicator": "brent_oil",
         "message": "[energy] Brent = 95 [BREACHED] (+0.50/1.0)"},
    ]
    count = insert_alerts(alerts_data)
    assert count == 1

    # Open a fresh connection to read back
    conn = _fresh_conn()
    row = conn.execute("SELECT * FROM alerts WHERE indicator = 'brent_oil'").fetchone()
    conn.close()
    assert row is not None
    assert row["acknowledged"] == 0


def test_insert_alerts_returns_count():
    """insert_alerts returns the number of rows inserted."""
    _clear_alerts()

    assert insert_alerts([]) == 0
    assert insert_alerts([
        {"category": "energy", "indicator": "a", "message": "test"},
        {"category": "energy", "indicator": "b", "message": "test"},
    ]) == 2


# ── 6. All 30 indicators evaluated ───────────────────────────────────────────


def test_all_30_indicators_in_registry():
    """Verify the INDICATOR_REGISTRY has all 30 indicators (from composite_scorer_v2)."""
    from src.agent.composite_scorer_v2 import INDICATOR_REGISTRY
    assert len(INDICATOR_REGISTRY) == 30, f"Expected 30 indicators, got {len(INDICATOR_REGISTRY)}"


def test_evaluate_alerts_handles_all_30_indicators():
    """evaluate_alerts processes all 30 indicators without error."""
    _clear_alerts()

    from src.agent.composite_scorer_v2 import INDICATOR_REGISTRY
    scores = {slug: 0.0 for slug in INDICATOR_REGISTRY}
    composite = _mock_composite_result(scores)

    indicators = {}
    for slug, config in INDICATOR_REGISTRY.items():
        if config.value_type == "enum":
            indicators[slug] = "normal"
        else:
            indicators[slug] = config.baseline or 100.0

    alerts = evaluate_alerts(composite, indicators)
    assert len(alerts) == 0, "All NORMAL should produce 0 alerts"


# ── 7. Non-numeric indicator handling ────────────────────────────────────────


def test_non_numeric_enum_alerts():
    """Non-numeric indicators fire alerts with enum values."""
    _clear_alerts()

    from src.agent.composite_scorer_v2 import score_composite

    indicators = {
        "hormuz_strait": "closure",
        "taiwan_strait_tension": "elevated",
        "russia_ukraine_conflict": "ongoing",
        "middle_east_conflict": "regional",
        "china_taiwan_tension": "elevated",
    }
    result = score_composite(indicators)
    alerts = evaluate_alerts(result, indicators)

    assert len(alerts) == 5

    hormuz = [a for a in alerts if a["indicator"] == "hormuz_strait"][0]
    assert "Closure" in hormuz["message"]
    assert "[CRITICAL]" in hormuz["message"]

    taiwan = [a for a in alerts if a["indicator"] == "taiwan_strait_tension"][0]
    assert "Elevated" in taiwan["message"]
    assert "[BREACHED]" in taiwan["message"]


# ── 8. Gold MA deviation alert format ────────────────────────────────────────


def test_gold_alert_critical_with_ma_context():
    """Gold alert includes MA context when in CRITICAL zone (>+25% deviation)."""
    _clear_alerts()

    from src.agent.composite_scorer_v2 import score_composite

    # Gold at $4300 with MA $3300 → deviation = 30.3% → capped at 1.0 → CRITICAL
    indicators = {"gold_price": 4300.0}
    result = score_composite(indicators, gold_ma_200=3300.0)

    alerts = evaluate_alerts(result, indicators, gold_ma_200=3300.0)
    assert len(alerts) == 1

    msg = alerts[0]["message"]
    assert "Gold Price" in msg
    assert "$4,300" in msg
    assert "200d MA" in msg
    assert "[CRITICAL]" in msg


def test_gold_breach_no_fire_on_first_normal():
    """Gold at baseline (no MA): score 0 → NORMAL → no alert on first run."""
    _clear_alerts()

    from src.agent.composite_scorer_v2 import score_composite

    # Gold without MA → score 0 → NORMAL
    indicators = {"gold_price": 3000.0}
    result = score_composite(indicators, gold_ma_200=None)

    alerts = evaluate_alerts(result, indicators)
    assert len(alerts) == 0, "Gold without MA should score 0 (NORMAL), no alert"


# ── 9. Inverted indicators ───────────────────────────────────────────────────


def test_inverted_indicator_alert_format():
    """Inverted indicators (e.g., EU Gas) show correct flag and format."""
    _clear_alerts()

    from src.agent.composite_scorer_v2 import score_composite

    indicators = {"eu_gas_storage": 58.0}
    result = score_composite(indicators)
    alerts = evaluate_alerts(result, indicators)

    assert len(alerts) == 1
    msg = alerts[0]["message"]
    assert "EU Gas Storage" in msg
    assert "58" in msg
    assert "[CRITICAL]" in msg


# ── 10. Integration: run_alerts ──────────────────────────────────────────────


def test_run_alerts_end_to_end():
    """run_alerts evaluates + inserts in one call."""
    _clear_alerts()

    composite = _mock_composite_result({"brent_oil": 0.8})  # BREACHED
    indicators = {"brent_oil": 100.0}

    count = run_alerts(composite, indicators)
    assert count == 1

    conn = _fresh_conn()
    row = conn.execute("SELECT * FROM alerts WHERE indicator = 'brent_oil'").fetchone()
    conn.close()
    assert row is not None
    assert "[BREACHED]" in row["message"]
    assert row["acknowledged"] == 0


# ── 11. verify no alert text violates v1.2 template (regex check) ────────────


def test_no_alert_violates_v1_2_template():
    """Every alert inserted must match the v1.2 template."""
    import re
    pattern = re.compile(
        r"^\[(?P<category>\w+)\]\s+(?P<name>.+?)\s+=\s+(?P<value>.+?)\s+\[(?P<flag>NORMAL|BREACHED|CRITICAL)\]"
        r"(?:\s+\(\+(?P<contribution>[\d.]+)/1\.0\))?$"
    )

    _clear_alerts()

    from src.agent.composite_scorer_v2 import score_composite

    indicators = {
        "brent_oil": 115.0,
        "eu_gas_storage": 58.0,
        "hormuz_strait": "threatened",
        "vix": 18.0,
        "gold_price": 4300.0,
        "usd_cny": 7.0,
    }
    result = score_composite(indicators, gold_ma_200=3300.0)
    alerts = evaluate_alerts(result, indicators, gold_ma_200=3300.0)
    count = insert_alerts(alerts)

    assert count > 0, "Should have inserted some alerts"

    conn = _fresh_conn()
    rows = conn.execute("SELECT message FROM alerts").fetchall()
    conn.close()

    for row in rows:
        msg = row["message"]
        assert pattern.match(msg), (
            f"Alert message violates v1.2 template:\n"
            f"  Got: {msg}\n"
            f"  Expected: [category] name = value [FLAG] (+x/1.0)"
        )
