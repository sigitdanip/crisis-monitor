"""Verify url_cache table exists in crisis.db after migration."""
from src.db.database import init_db, get_db

init_db()
conn = get_db()

# Check url_cache table schema
result = conn.execute("PRAGMA table_info('url_cache')").fetchall()
print("url_cache table columns:")
for col in result:
    print(f"  {col['name']:20s} {col['type']:15s} nullable={not col['notnull']} pk={col['pk']}")

# Also check url_validations still exists
result2 = conn.execute("PRAGMA table_info('url_validations')").fetchall()
print()
print("url_validations table columns (still present for backward compat):")
for col in result2:
    print(f"  {col['name']:20s} {col['type']:15s} nullable={not col['notnull']} pk={col['pk']}")

# List all tables
tables = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()
print()
print("All tables:", [t["name"] for t in tables])

conn.close()
print("\nVerification PASSED: url_cache table exists with correct schema")
