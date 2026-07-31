"""Backfill incomplete runs from response_times data."""

import sqlite3

db_file = "query_response_times.db"

conn = sqlite3.connect(db_file)
cursor = conn.cursor()

# Find runs still marked running
cursor.execute("SELECT run_id FROM runs WHERE status = 'running'")
orphaned = [r[0] for r in cursor.fetchall()]

for run_id in orphaned:
    # Get max timestamp from responses
    cursor.execute(
        "SELECT MAX(timestamp) FROM response_times WHERE run_id = ?", (run_id,)
    )
    max_ts = cursor.fetchone()[0]

    if not max_ts:
        # No responses, drop it
        cursor.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        print(f"Dropped {run_id} (no responses)")
    else:
        # Close with max timestamp
        cursor.execute(
            "UPDATE runs SET end_time = ?, status = 'backfilled' WHERE run_id = ?",
            (max_ts, run_id),
        )
        print(f"Closed {run_id} at {max_ts}")

conn.commit()
conn.close()
