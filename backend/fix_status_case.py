"""Fix existing indicator_history rows: convert uppercase statuses to lowercase."""
import sys
sys.path.insert(0, '/root/crisis-monitor/backend/src')
from db.database import get_db

STATUS_MAP = {
    'NORMAL': 'normal',
    'CRITICAL': 'critical',
    'BREACHED': 'breached',
    'UNKNOWN': 'unknown',
    'UNASSESSED': 'normal',
    'ELEVATED': 'elevated',
}

conn = get_db()
rows = conn.execute("SELECT id, status FROM indicator_history").fetchall()
updated = 0
for r in rows:
    old_status = r['status']
    new_status = STATUS_MAP.get(old_status)
    if new_status and new_status != old_status:
        conn.execute("UPDATE indicator_history SET status = ? WHERE id = ?", (new_status, r['id']))
        updated += 1

conn.commit()
print(f"Updated {updated} rows to lowercase statuses")

# Verify
remaining = conn.execute("SELECT DISTINCT status FROM indicator_history").fetchall()
print(f"Distinct statuses now: {[r['status'] for r in remaining]}")
conn.close()
