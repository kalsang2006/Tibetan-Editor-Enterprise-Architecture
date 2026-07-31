"""Audit helper script for database indexes and metrics."""

from pathlib import Path
from teea.persistence import DatabaseManager

db = DatabaseManager(Path("Data/Processed/teea.db"))
cursor = db._conn.cursor()
cursor.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index'")
rows = cursor.fetchall()

print(f"Total SQLite Indexes: {len(rows)}")
for name, tbl_name, sql in rows:
    print(f"  - Index: {name} on table `{tbl_name}` -> {sql}")
