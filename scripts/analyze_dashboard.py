#!/usr/bin/env python3
"""Quick dashboard analysis"""
import json, urllib.request, sys
from collections import Counter

def fetch(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())

# Dashboard
dash = fetch("http://localhost:8001/api/dashboard")
indicators = dash['indicators']
print(f"Total indicators: {len(indicators)}")
null_indicators = [i for i in indicators if i['value'] is None]
print(f"Null-value indicators ({len(null_indicators)}):")
for i in null_indicators:
    print(f"  {i['name']} ({i['category']}): value=null")

cats = Counter(i['category'] for i in indicators)
print(f"Categories: {dict(cats)}")

# Dots
dots = dash['dots']
print(f"\nTotal dots: {len(dots)}")
for d in dots:
    unavailable = 'data unavailable' in d.get('summary','') or 'data unavailable' in str(d.get('key_signals',''))
    llm_fallback = 'LLM analysis unavailable' in d.get('summary','')
    print(f"  {d['dot_name']}: status={d['status']}, unavailable={unavailable}, llm_fallback={llm_fallback}")

# Report
r = dash['report']
print(f"\nReport id: {r['id']}")
print(f"Confidence: {r['confidence']} (type={type(r['confidence']).__name__})")
print(f"Composite score: {r['composite_score']}")
print(f"Synthesis len: {len(r['synthesis'])} chars")
print(f"Synthesis: {r['synthesis'][:150]}")

q = r.get('five_questions', {})
for k,v in q.items():
    ans = v.get('answer','') if isinstance(v, dict) else v
    print(f"  {k}: empty={not ans}, len={len(ans)}")

# Reports history
try:
    reports = fetch("http://localhost:8001/api/reports/history")
    if isinstance(reports, list) and reports:
        latest = reports[0]
        print(f"\nLatest report (history): id={latest.get('id')}, confidence={latest.get('confidence')}, composite={latest.get('composite_score')}, synth_len={len(latest.get('synthesis',''))}")
except Exception as e:
    print(f"\nReports history error: {e}")
