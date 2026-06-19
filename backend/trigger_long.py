"""Trigger pipeline with longer timeout (5 min)."""
import json
import urllib.request

print("Triggering pipeline (timeout 300s)...")
req = urllib.request.Request("http://localhost:8001/api/trigger/daily", method="POST")
try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read())
    print(f"Status: {result.get('status')}")
    print(f"Composite: {result.get('composite_score')}")
    print(f"Duration: {result.get('total_duration_ms', 0):.0f}ms")
    print(f"Success count: {result.get('success_count')}")
    if result.get('errors'):
        print(f"Errors: {result['errors']}")
except Exception as e:
    print(f"FAILED: {e}")
