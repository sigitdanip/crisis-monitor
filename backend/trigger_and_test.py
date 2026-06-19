"""Trigger a daily pipeline run and check results."""
import json
import urllib.request
import time

# 1. Trigger
print("Triggering pipeline...")
req = urllib.request.Request("http://localhost:8001/api/trigger/daily", method="POST")
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    print(f"  Status: {result.get('status')}")
    print(f"  Composite score: {result.get('composite_score')}")
    print(f"  Duration: {result.get('total_duration_ms', 0):.0f}ms")
    print(f"  Success count: {result.get('success_count')}")
    if result.get('errors'):
        print(f"  Errors: {result['errors']}")
except Exception as e:
    print(f"  FAILED: {e}")
    raise SystemExit(1)

# 2. Wait a moment
time.sleep(1)

# 3. Check dashboard
print("\nChecking dashboard...")
with urllib.request.urlopen("http://localhost:8001/api/dashboard") as resp:
    data = json.loads(resp.read())

indicators = data.get("indicators", [])
print(f"  Indicators: {len(indicators)}")

# Check that new columns are populated
empty_meta = [i['name'] for i in indicators if not i.get('category')]
if empty_meta:
    print(f"  WARNING — {len(empty_meta)} indicators missing category: {empty_meta[:5]}")
else:
    print("  OK — all indicators have category")

empty_unit = [i['name'] for i in indicators if not i.get('unit')]
if empty_unit:
    print(f"  WARNING — {len(empty_unit)} indicators missing unit")
else:
    print("  OK — all indicators have unit")

# Print first 5 with full details
print("\nFirst 5 indicators:")
for i in indicators[:5]:
    print(f"  {i['name']}: {i['value']} {i['unit']} [{i['status']}] — {i['category']} (trigger: {i.get('trigger_level','N/A')})")

print("\nDone.")
