"""Database and configuration management for Locust load tests."""

import json
import sqlite3
import threading
import tomllib
from datetime import UTC, datetime
from pathlib import Path
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

    def record_response(
        self, query_name, response_time, status_code, success, error_message
    ):
        """Record a single request's response time to the database."""
        timestamp = datetime.now(UTC).isoformat()

        with self.db_lock:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO response_times
                (run_id, timestamp, query_name, response_time_ms, status_code, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    self.run_id,
                    timestamp,
                    query_name,
                    response_time,
                    status_code,
                    success,
                    error_message,
                ),
            )
            conn.commit()
            conn.close()
