#!/usr/bin/env python3
import sqlite3
from datetime import datetime, timedelta, timezone

DB = "query_response_times.db"
CUTOFF = datetime.now(timezone.utc) - timedelta(days=30)

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute(
    "SELECT COUNT(*), COUNT(DISTINCT run_id) FROM response_times WHERE run_id IN (SELECT run_id FROM runs WHERE start_time < ?)",
    (CUTOFF.isoformat(),),
)
rows, run_ids = cur.fetchone()

cur.execute(
    "DELETE FROM response_times WHERE run_id IN (SELECT run_id FROM runs WHERE start_time < ?)",
    (CUTOFF.isoformat(),),
)
cur.execute("DELETE FROM runs WHERE start_time < ?", (CUTOFF.isoformat(),))
conn.commit()

print(f"Deleted {rows:,} rows from {run_ids} old runs (cutoff: {CUTOFF.date()})")
