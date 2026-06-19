"""Test the frontend proxy to backend."""
import urllib.request
import json

# Test direct backend
try:
    resp = urllib.request.urlopen('http://localhost:8001/health')
    print(f"Backend health: {resp.read().decode()}")
except Exception as e:
    print(f"Backend health FAILED: {e}")

# Test through frontend proxy (if frontend running)
try:
    resp = urllib.request.urlopen('http://localhost:3001/api/dashboard')
    data = json.loads(resp.read())
    indicators = data.get('indicators', [])
    print(f"\nFrontend proxy indicators: {len(indicators)}")
except Exception as e:
    print(f"\nFrontend proxy FAILED: {e}")

# Try port 3000 (default Next.js)
try:
    resp = urllib.request.urlopen('http://localhost:3000/api/dashboard')
    data = json.loads(resp.read())
    indicators = data.get('indicators', [])
    print(f"Frontend :3000 indicators: {len(indicators)}")
except Exception as e:
    print(f"Frontend :3000 FAILED: {e}")
