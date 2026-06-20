#!/usr/bin/env python3
"""Query indicator_history table for AC1 validation"""
import sqlite3, sys
from datetime import datetime, timedelta

DB = "/root/crisis-monitor/backend/data/crisis.db"
TODAY = datetime.now().strftime("%Y-%m-%d")
CUTOFF = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

conn = sqlite3.connect(DB)
cur = conn.cursor()

# Count distinct indicators
cur.execute("SELECT COUNT(DISTINCT indicator_name) FROM indicator_history")
count = cur.fetchone()[0]
print(f"AC1.1 - Distinct indicator count: {count} (expected: 26)")

# Get last recorded_at per indicator
cur.execute("""
    SELECT indicator_name, MAX(recorded_at) as last_recorded 
    FROM indicator_history 
    GROUP BY indicator_name 
    ORDER BY indicator_name
""")
rows = cur.fetchall()
print(f"\nAC1.2 - Indicator freshness (cutoff: {CUTOFF}):")
all_fresh = True
for name, ts in rows:
    fresh = ts >= CUTOFF
    if not fresh:
        all_fresh = False
    flag = "FRESH" if fresh else "STALE"
    print(f"  {name}: {ts} [{flag}]")

print(f"\n  All fresh: {all_fresh}")

# Category coverage
cur.execute("""
    SELECT DISTINCT ih.indicator_name 
    FROM indicator_history ih
    WHERE ih.recorded_at >= ?
""", (CUTOFF,))
fresh_names = [r[0] for r in cur.fetchall()]

# Hardcoded category mapping from indicator_narrator.py
CATEGORY_MAP = {
    "ig_oas": "Credit", "hy_oas": "Credit",
    "btp_bund_spread": "Debt", "cds_doubling": "Debt",
    "caixin_pmi": "China", "china_property_default": "China",
    "brent_price": "Energy", "wti_price": "Energy", "natgas_price": "Energy",
    "eu_gas_storage": "Energy", "us_spr": "Energy",
    "dxy": "Financial", "gold_price": "Financial", "us_10y": "Financial",
    "us_2y": "Financial", "vix": "Financial",
    "cme_grains_monthly_pct": "Food", "fao_monthly_change_pct": "Food",
    "hormuz_closure": "Geopolitical", "nato_fracture": "Geopolitical",
    "us_nato_withdrawal": "Geopolitical",
    "govt_crisis": "Political", "protest_countries": "Political",
    "egp_breach": "EM Currency", "idr_breach": "EM Currency", "try_breach": "EM Currency",
}

covered = set()
for name in fresh_names:
    cat = CATEGORY_MAP.get(name, "Unknown")
    covered.add(cat)

expected_cats = {"Credit", "Energy", "China", "Debt", "Food", "Geopolitical", "Political", "Financial", "EM Currency", "Supply Chain"}
missing = expected_cats - covered
print(f"\nAC1.3 - Category coverage: {sorted(covered)}")
print(f"  Missing categories: {missing if missing else 'none'}")

conn.close()

# Summary
print(f"\n=== AC1 SUMMARY ===")
print(f"  1.1 Row count (26): {'PASS' if count == 26 else 'FAIL'} ({count})")
print(f"  1.2 All fresh (24h): {'PASS' if all_fresh else 'FAIL'}")
print(f"  1.3 Category coverage: {'PASS' if not missing else 'FAIL'} (missing: {missing})")
