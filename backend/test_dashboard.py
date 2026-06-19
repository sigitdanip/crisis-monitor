"""Test the dashboard API and print indicator data."""
import json
import urllib.request

try:
    with urllib.request.urlopen("http://localhost:8001/api/dashboard") as resp:
        data = json.loads(resp.read())
    indicators = data.get("indicators", [])
    print(f"Indicators: {len(indicators)}")
    for i in indicators[:8]:
        print(f"  {i['name']}: {i['value']} {i.get('unit','?')} [{i.get('status','?')}] cat={i.get('category','?')} trigger={i.get('trigger_level','?')}")
except Exception as e:
    print(f"Error: {e}")
    print("Backend may not be running on port 8001")
