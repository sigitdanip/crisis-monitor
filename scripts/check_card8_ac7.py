#!/usr/bin/env python3
"""Verify Card 8 ACs and remaining checks"""
import json, os, sys, urllib.request, urllib.error

B = "http://localhost:8001"
TOKEN = os.environ.get("CRISIS_TRIGGER_TOKEN")
if not TOKEN:
    TOKEN = input("Enter CRISIS_TRIGGER_TOKEN: ").strip()
    if not TOKEN:
        print("ERROR: CRISIS_TRIGGER_TOKEN required (env var or stdin)", file=sys.stderr)
        sys.exit(1)

def post(url, headers=None, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k,v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

# Idempotency: trigger twice rapidly
print("=== IDEMPOTENCY ===")
s1, r1 = post(f"{B}/api/trigger/daily", {"X-Crisis-Token": TOKEN})
print(f"Trigger 1: status={s1}, resp={json.dumps(r1)}")
s2, r2 = post(f"{B}/api/trigger/daily", {"X-Crisis-Token": TOKEN})
print(f"Trigger 2: status={s2}, resp={json.dumps(r2)}")
if s2 == 409 or ("already" in str(r2).lower()):
    print("IDEMPOTENCY: likely working (409/conflict on duplicate)")
else:
    print(f"IDEMPOTENCY: unclear - second trigger returned {s2}")

# Test no stack traces - hit a bad endpoint
print("\n=== STACK TRACE CHECK ===")
for path in ["/api/nonexistent", "/api/dashboard/../etc"]:
    status = 0
    try:
        with urllib.request.urlopen(f"{B}{path}") as r:
            body = r.read().decode()
            status = r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        status = e.code
    except Exception as ex:
        body = str(ex)
        status = -1
    has_tb = "Traceback" in body or "File \"" in body
    print(f"  {path}: status={status}, stack_trace={has_tb}")

# Check pipeline status again
print("\n=== PIPELINE STATUS ===")
with urllib.request.urlopen(f"{B}/api/pipeline/status") as r:
    d = json.loads(r.read())
print(f"last_run: {d['last_run']}")
for n in d['nodes']:
    if 'Agent' in n['id']:
        print(f"  {n['id']}: {n['status']} | {n.get('error','')[:60]}")

# Check AC7: Data source coverage via dashboard
print("\n=== DATA SOURCE COVERAGE (AC7) ===")
with urllib.request.urlopen(f"{B}/api/dashboard") as r:
    dash = json.loads(r.read())

# Check unavailable strings in dots
dots = dash['dots']
for d in dots:
    summary = d.get('summary','')
    sources = d.get('sources','')
    has_unavail = 'unavailable' in str(d).lower()
    if has_unavail:
        print(f"  {d['dot_name']}: UNAVAILABLE in response")

# Check BTP-Bund
indicators = dash['indicators']
btp = [i for i in indicators if 'BTP' in i['name']]
if btp:
    ind = btp[0]
    print(f"  BTP-Bund Spread: value={ind['value']}, null={ind['value'] is None}")

# Check 4 news-derived indicators
news_names = ['Caixin', 'EU Gas', 'US SPR', 'Protest']
for name in news_names:
    found = [i for i in indicators if name.lower() in i['name'].lower()]
    for ind in found:
        narrative = ind.get('narrative','')
        print(f"  {ind['name']}: value={ind['value']}, narrative_len={len(narrative)}, narrative='{narrative[:80]}'")
