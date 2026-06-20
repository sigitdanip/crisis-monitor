#!/usr/bin/env python3
"""Extended analysis: reports history, health, trigger auth, idempotency"""
import json, urllib.request, urllib.error

def fetch(url, headers=None):
    req = urllib.request.Request(url)
    if headers:
        for k,v in headers.items():
            req.add_header(k,v)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

# Reports history
code, data = fetch("http://localhost:8001/api/reports/history")
print(f"=== REPORTS HISTORY (status={code}) ===")
if isinstance(data, list):
    print(f"Count: {len(data)}")
    if data:
        latest = data[0]
        print(f"Latest: id={latest.get('id')}, confidence={latest.get('confidence')}, composite={latest.get('composite_score')}")
        print(f"  synthesis_len={len(latest.get('synthesis',''))}")
        print(f"  end_state={latest.get('end_state')}")
        q = latest.get('five_questions',{})
        for k,v in q.items():
            print(f"  {k}: answer_empty={not v.get('answer','')}")
else:
    print(str(data)[:300])

# Health
code, data = fetch("http://localhost:8001/api/system/health")
print(f"\n=== SYSTEM HEALTH (status={code}) ===")
print(json.dumps(data, indent=2))

# Trigger without auth
code, data = fetch("http://localhost:8001/api/trigger/daily", {"Content-Type": "application/json"})
print(f"\n=== TRIGGER WITHOUT AUTH (status={code}) ===")
print(str(data)[:200])

# Trigger with wrong auth
code, data = fetch("http://localhost:8001/api/trigger/daily", {"X-Crisis-Token": "wrong-token"})
print(f"\n=== TRIGGER WITH WRONG TOKEN (status={code}) ===")
print(str(data)[:200])

# Idempotency - trigger twice in 60s
print(f"\n=== IDEMPOTENCY CHECK ===")
# First trigger (need valid token)
code1, data1 = fetch("http://localhost:8001/api/trigger/daily", {"X-Crisis-Token": "CHANGE_ME_IN_PRODUCTION"})
print(f"First trigger: status={code1}, response={str(data1)[:200]}")
# Second trigger immediately
code2, data2 = fetch("http://localhost:8001/api/trigger/daily", {"X-Crisis-Token": "CHANGE_ME_IN_PRODUCTION"})
print(f"Second trigger: status={code2}, response={str(data2)[:200]}")

# Pipeline status
code, data = fetch("http://localhost:8001/api/pipeline/status")
print(f"\n=== PIPELINE STATUS (status={code}) ===")
print(json.dumps(data, indent=2)[:500] if isinstance(data, dict) else str(data)[:300])
