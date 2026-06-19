"""Check old vs new indicator_history rows."""
import sys
sys.path.insert(0, '/root/crisis-monitor/backend/src')
from db.database import get_db

conn = get_db()

# Check: rows with empty vs populated display_name
total = conn.execute("SELECT COUNT(*) FROM indicator_history").fetchone()[0]
with_display = conn.execute("SELECT COUNT(*) FROM indicator_history WHERE display_name != ''").fetchone()[0]
with_category = conn.execute("SELECT COUNT(*) FROM indicator_history WHERE category != ''").fetchone()[0]
with_unit = conn.execute("SELECT COUNT(*) FROM indicator_history WHERE unit != ''").fetchone()[0]

print(f"Total rows: {total}")
print(f"With display_name: {with_display}")
print(f"With category: {with_category}")
print(f"With unit: {with_unit}")

# Show sample old row (no metadata)
print("\nOld row sample (no metadata):")
old = conn.execute("SELECT * FROM indicator_history WHERE display_name = '' LIMIT 1").fetchone()
if old:
    print(f"  indicator_name={old['indicator_name']}, value={old['value']}, display_name='{old['display_name']}', category='{old['category']}'")

# Show the COALESCE query result for old row
print("\nDashboard query test on old row:")
r = conn.execute("""
    SELECT COALESCE(NULLIF(display_name, ''), indicator_name) as name,
           COALESCE(category, '') as category,
           value, COALESCE(unit, '') as unit, status
    FROM indicator_history WHERE display_name = '' LIMIT 1
""").fetchone()
if r:
    name = r['name']
    cat = r['category']
    val = r['value']
    unit = r['unit']
    print(f"  name={name}, category='{cat}', value={val}, unit='{unit}'")

conn.close()
