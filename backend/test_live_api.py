"""Hit the running API."""
import urllib.request
import json

try:
    # Health check
    resp = urllib.request.urlopen('http://localhost:8001/health')
    print(f"Health: {resp.read().decode()}")

    # Dashboard
    resp = urllib.request.urlopen('http://localhost:8001/api/dashboard')
    data = json.loads(resp.read())
    indicators = data.get('indicators', [])
    print(f"\nDashboard indicators: {len(indicators)} rows")
    for ind in indicators[:3]:
        print(json.dumps(ind, default=str))
    
    dots = data.get('dots', [])
    print(f"\nDots: {len(dots)}")
    
    pathways = data.get('pathways', [])
    print(f"Pathways: {len(pathways)}")
    
except Exception as e:
    print(f"Error: {e}")
