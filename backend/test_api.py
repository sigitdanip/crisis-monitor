"""Test the dashboard API endpoint."""
import sys
sys.path.insert(0, '/root/crisis-monitor/backend/src')

# Query database directly using the same query as routes.py
from db.database import get_db

conn = get_db()

indicators = conn.execute("""
    SELECT COALESCE(NULLIF(display_name, ''), indicator_name) as name,
           COALESCE(category, '') as category,
           value, COALESCE(unit, '') as unit,
           status, COALESCE(trigger_level, '') as trigger_level,
           COALESCE(narrative, '') as narrative,
           recorded_at as fetched_at
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY indicator_name ORDER BY recorded_at DESC) as rn
        FROM indicator_history
    ) WHERE rn = 1
    ORDER BY category, indicator_name
""").fetchall()

print(f"Dashboard indicator query returned {len(indicators)} rows")
for r in indicators:
    d = dict(r)
    print(f"  name={d['name']}, category='{d['category']}', value={d['value']}, unit='{d['unit']}', status={d['status']}")

if not indicators:
    print("NO INDICATORS RETURNED!")

# Also check what unique indicator_names exist
print("\n--- Unique indicator_names in indicator_history ---")
names = conn.execute("SELECT DISTINCT indicator_name FROM indicator_history ORDER BY indicator_name").fetchall()
for n in names:
    cnt = conn.execute("SELECT COUNT(*) FROM indicator_history WHERE indicator_name = ?", (n[0],)).fetchone()[0]
    print(f"  {n[0]}: {cnt} rows")

conn.close()
