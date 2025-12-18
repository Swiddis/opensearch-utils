"""Database and configuration management for Locust load tests."""

import json
import sqlite3
import threading
import time
import tomllib
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from queue import Queue
from uuid import uuid4


def load_config():
    """Load configuration from config.toml file."""
    config_path = Path("config.toml")
    if not config_path.exists():
        raise FileNotFoundError(
            "config.toml not found. Please create a configuration file."
        )
    with open(config_path, "rb") as f:
        return tomllib.load(f)


class DatabaseManager:
    """Manages SQLite database operations for load test tracking."""

    def __init__(self, config):
        self.config = config
        self.db_file = config["database"]["file"]
        self.run_id = str(uuid4())
        self.db_lock = threading.Lock()

        # Batch writing configuration
        self.batch_size = config["database"].get("batch_size", 100)
        self.flush_interval = config["database"].get("flush_interval", 1.0)
        self.record_queue = Queue()
        self.writer_running = True

        # Start background writer thread
        self.writer_thread = threading.Thread(target=self._batch_writer, daemon=True)
        self.writer_thread.start()

    def init_database(self):
        """Initialize the SQLite database and create necessary tables."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        # Create response_times table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS response_times (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                query_name TEXT NOT NULL,
                response_time_ms REAL NOT NULL,
                status_code INTEGER,
                success INTEGER NOT NULL,
                error_message TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_query_name ON response_times(query_name)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_timestamp ON response_times(timestamp)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_run_id ON response_times(run_id)
        """
        )

        # Create runs table for tracking run metadata
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                start_time TEXT NOT NULL,
                end_time TEXT,
                status TEXT NOT NULL,
                config_snapshot TEXT
            )
        """
        )

        conn.commit()
        conn.close()

    def start_run(self):
        """Record the start of a new load test run."""
        start_time = datetime.now(UTC).isoformat()
        tracking_method = self.config["run_tracking"]["method"]

        if tracking_method == "database":
            config_snapshot = json.dumps(self.config, indent=2)
            with self.db_lock:
                conn = sqlite3.connect(self.db_file)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO runs (run_id, start_time, status, config_snapshot)
                    VALUES (?, ?, ?, ?)
                """,
                    (self.run_id, start_time, "running", config_snapshot),
                )
                conn.commit()
                conn.close()
            print(f"Started run {self.run_id} at {start_time}")
        elif tracking_method == "file":
            run_file = self.config["run_tracking"].get("file", "run_ids.txt")
            with open(run_file, "a") as fp:
                fp.write(f"{start_time} -- {self.run_id} -- started\n")
            print(f"Started run {self.run_id} (logged to {run_file})")
        else:
            raise ValueError(f"Invalid run_tracking.method: {tracking_method}")

    def end_run(self, status="completed"):
        """Record the end of a load test run."""
        tracking_method = self.config["run_tracking"]["method"]
        end_time = datetime.now(UTC).isoformat()

        if tracking_method == "database":
            with self.db_lock:
                conn = sqlite3.connect(self.db_file)
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE runs SET end_time = ?, status = ?
                    WHERE run_id = ?
                """,
                    (end_time, status, self.run_id),
                )
                conn.commit()
                conn.close()
            print(f"Ended run {self.run_id} at {end_time} with status: {status}")
        elif tracking_method == "file":
            run_file = self.config["run_tracking"].get("file", "run_ids.txt")
            with open(run_file, "a") as fp:
                fp.write(f"{end_time} -- {self.run_id} -- {status}\n")

    def _batch_writer(self):
        """Background thread that writes batched records to the database."""
        batch = []
        last_flush = time.time()

        while self.writer_running or not self.record_queue.empty():
            try:
                # Try to get a record with timeout
                timeout = max(0.1, self.flush_interval - (time.time() - last_flush))
                record = self.record_queue.get(timeout=timeout)
                batch.append(record)

                # Flush if batch is full or interval elapsed
                should_flush = (
                    len(batch) >= self.batch_size
                    or (time.time() - last_flush) >= self.flush_interval
                )

                if should_flush:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.time()

            except Exception:
                # Timeout or queue empty - flush if we have data and interval elapsed
                if batch and (time.time() - last_flush) >= self.flush_interval:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.time()

        # Final flush of any remaining records
        if batch:
            self._flush_batch(batch)

    def _flush_batch(self, batch):
        """Flush a batch of records to the database."""
        if not batch:
            return

        with self.db_lock:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO response_times
                (run_id, timestamp, query_name, response_time_ms, status_code, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                batch,
            )
            conn.commit()
            conn.close()

    def record_response(
        self, query_name, response_time, status_code, success, error_message
    ):
        """Record a single request's response time to the queue for batch writing."""
        timestamp = datetime.now(UTC).isoformat()

        record = (
            self.run_id,
            timestamp,
            query_name,
            response_time,
            status_code,
            success,
            error_message,
        )
        self.record_queue.put(record)

    def flush_remaining(self):
        """Stop the writer thread and flush all remaining records."""
        self.writer_running = False
        self.writer_thread.join(timeout=10.0)  # Wait up to 10 seconds for flush
