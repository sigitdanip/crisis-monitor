#!/usr/bin/env python3
"""Check pipeline status"""
import json, urllib.request

with urllib.request.urlopen("http://localhost:8001/api/pipeline/status") as r:
    d = json.loads(r.read())

print(f"last_run: {d['last_run']}")
print(f"nodes: {len(d['nodes'])}")
for n in d['nodes']:
    err = n.get('error', '')
    print(f"  {n['id']}: {n['status']} | err={err[:80] if err else 'none'}")
print(f"success_count: {d.get('success_count', 'N/A')}")
