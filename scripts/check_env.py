#!/usr/bin/env python3
"""Check env vars as seen by backend"""
import os
for var in ['OPENCODE_GO_API_KEY', 'CRISIS_TRIGGER_TOKEN', 'NEWS_API_KEY', 'FRED_API_KEY']:
    val = os.environ.get(var, '')
    print(f'{var}: {"SET" if val else "NOT SET"} (len={len(val)})')
