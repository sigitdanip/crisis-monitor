"""End-to-end verification of indicator fixes."""
import sys
sys.path.insert(0, '/root/crisis-monitor/backend/src')

# 1. Test _assess fixes
from agent.indicator_narrator import _assess, INDICATOR_META, _parse_trigger_value

print("=== 1. _assess edge cases ===")

# Percentage triggers
result = _assess(5.1, INDICATOR_META["fao_monthly_change_pct"])
print(f"FAO FPI 5.1% (trigger >10%): {result} (expect normal)")
assert result == "normal", f"Expected normal, got {result}"

result = _assess(12.0, INDICATOR_META["fao_monthly_change_pct"])
print(f"FAO FPI 12% (trigger >10%): {result} (expect critical)")
assert result == "critical", f"Expected critical, got {result}"

# Flag indicators
result = _assess(1, INDICATOR_META["try_breach"])
print(f"TRY Breach=1 (flag): {result} (expect breached)")
assert result == "breached", f"Expected breached, got {result}"

result = _assess(0, INDICATOR_META["try_breach"])
print(f"TRY Breach=0 (flag): {result} (expect normal)")
assert result == "normal", f"Expected normal, got {result}"

# Empty string
result = _assess("", INDICATOR_META["hormuz_closure"])
print(f"Hormuz Closure='' (status): {result} (expect unknown)")
assert result == "unknown", f"Expected unknown, got {result}"

# None
result = _assess(None, INDICATOR_META["brent_price"])
print(f"None value: {result} (expect unknown)")
assert result == "unknown", f"Expected unknown, got {result}"

# String "closed"
result = _assess("closed", INDICATOR_META["hormuz_closure"])
print(f"Hormuz Closure='closed': {result} (expect critical)")
assert result == "critical", f"Expected critical, got {result}"

# Normal numeric (all lowercase now)
result = _assess(98.4, INDICATOR_META["brent_price"])
print(f"Brent 98.4 (trigger >100): {result} (expect normal)")
assert result == "normal", f"Expected normal, got {result}"

# _parse_trigger_value tests
print("\n=== 2. _parse_trigger_value ===")
assert _parse_trigger_value(">100") == 100.0, f"Failed >100: {_parse_trigger_value('>100')}"
assert _parse_trigger_value(">10%") == 10.0, f"Failed >10%: {_parse_trigger_value('>10%')}"
assert _parse_trigger_value("<48") == 48.0, f"Failed <48: {_parse_trigger_value('<48')}"
assert _parse_trigger_value("≥1") == 1.0, f"Failed ≥1: {_parse_trigger_value('≥1')}"
assert _parse_trigger_value("inversion") is None, f"Failed inversion: {_parse_trigger_value('inversion')}"
assert _parse_trigger_value("") is None, f"Failed empty: {_parse_trigger_value('')}"
print("All _parse_trigger_value tests pass")

# 3. Test database query
print("\n=== 3. Dashboard query ===")
from db.database import get_db
conn = get_db()
indicators = conn.execute("""
    SELECT COALESCE(NULLIF(display_name, ''), indicator_name) as name,
           COALESCE(category, '') as category,
           value, COALESCE(unit, '') as unit,
           status, COALESCE(trigger_level, '') as trigger_level,
           COALESCE(narrative, '') as narrative,
           recorded_at as fetched_at
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY indicator_name ORDER BY recorded_at DESC) as rn
        FROM indicator_history
    ) WHERE rn = 1
    ORDER BY category, indicator_name
""").fetchall()
print(f"Returned {len(indicators)} indicators")
assert len(indicators) > 0, "No indicators returned!"

for r in indicators:
    d = dict(r)
    # Verify all required fields present
    assert d['name'], f"Missing name for {d}"
    assert d['status'], f"Missing status for {d['name']}"
    assert d['category'] is not None, f"Missing category for {d['name']}"
    print(f"  {d['name']}: {d['value']} {d['unit']} [{d['status']}] — {d['category']}")

conn.close()

print("\n=== ALL CHECKS PASSED ===")
