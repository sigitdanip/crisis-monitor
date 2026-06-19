"""Verify DB migration: narrative column in indicator_history."""
from src.db.database import init_db

init_db()
print("DB init OK")

from src.db.database import get_db
conn = get_db()
cols = conn.execute("PRAGMA table_info(indicator_history)").fetchall()
col_names = [c[1] for c in cols]
print(f"indicator_history columns: {col_names}")
assert "narrative" in col_names, "narrative column missing!"
conn.close()
print("Migration verified")
