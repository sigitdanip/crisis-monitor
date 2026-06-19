"""Validate the indicator_history fix."""
import sys
sys.path.insert(0, '/root/crisis-monitor/backend/src')

from db.database import init_db, get_db, DB_PATH

# 1. Run migrations
print("1. Running init_db()...")
init_db()
print("   OK")

# 2. Check indicator_history columns
conn = get_db()
rows = conn.execute("PRAGMA table_info(indicator_history)").fetchall()
cols = [r['name'] for r in rows]
print(f"2. indicator_history columns: {cols}")
expected = ['id', 'indicator_name', 'display_name', 'category', 'value', 'unit', 'status', 'trigger_level', 'narrative', 'recorded_at']
missing = [e for e in expected if e not in cols]
if missing:
    print(f"   FAIL — missing columns: {missing}")
else:
    print("   OK — all columns present")

# 3. Check existing data count
count = conn.execute("SELECT COUNT(*) FROM indicator_history").fetchone()[0]
print(f"3. indicator_history row count: {count}")

# 4. Test the dashboard query (should work even with no new data, just empty)
try:
    result = conn.execute("""
        SELECT COALESCE(NULLIF(display_name, ''), indicator_name) as name,
               COALESCE(category, '') as category,
               value, COALESCE(unit, '') as unit,
               status, COALESCE(trigger_level, '') as trigger_level,
               recorded_at as fetched_at
        FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY indicator_name ORDER BY recorded_at DESC) as rn
            FROM indicator_history
        ) WHERE rn = 1
        ORDER BY category, indicator_name
    """).fetchall()
    print(f"4. Dashboard query returned {len(result)} rows — OK")
except Exception as e:
    print(f"4. Dashboard query FAILED: {e}")

conn.close()
print("\nValidation complete.")
