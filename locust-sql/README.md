# OpenSearch PPL in Locust

Quick set of files for load-testing OpenSearch PPL. For best results, make sure to resource-constrain OpenSearch to a handful of CPUs.

## Setup

1. Install dependencies using `uv`:
   ```sh
   uv sync
   ```

2. Create a `config.toml` file (see Configuration section below)

3. Run locust:
   ```sh
   uv run locust
   ```

## Configuration

The load test is configured via `config.toml`. A sample configuration:

```toml
[database]
# Path to SQLite database for storing response times
file = "query_response_times.db"

[calcite]
# Whether Calcite should be enabled in the cluster
enabled = true
# If true, will update the cluster setting; if false, will only check and fail if mismatch
enforce = true

[tests]
# Directory containing PPL query files
ppl_directory = "ppl-patterns"
# Patterns to exclude from test execution (queries containing these strings will be skipped)
exclude_patterns = ["range_auto_date", "headless"]

[run_tracking]
# How to track run IDs: "database" (recommended) or "file"
method = "database"
# Only used if method = "file"
file = "run_ids.txt"
```

### Configuration Options

#### `[database]`
- `file`: Path to the SQLite database where response times are stored. Each request's response time, status, and any errors are logged here for analysis.

#### `[calcite]`
- `enabled`: Whether the Calcite plugin should be enabled on the OpenSearch cluster (`true` or `false`)
- `enforce`: Controls behavior when cluster setting doesn't match config:
  - `true`: Automatically updates the cluster setting to match config
  - `false`: Only checks the setting and raises an error if there's a mismatch

#### `[tests]`
- `ppl_directory`: Directory containing `.ppl` files with PPL queries to test
- `exclude_patterns`: List of strings - any query file whose name contains these patterns will be excluded from testing

#### `[run_tracking]`
- `method`: How to track load test runs:
  - `"database"` (recommended): Stores run metadata in the database with start/end times, status, and config snapshot. Each run gets a unique UUID and can be queried from the `runs` table.
  - `"file"`: Legacy mode that appends run information to a text file
- `file`: Only used when `method = "file"` - specifies the filename for run tracking

## Database Schema

### `response_times` Table
Stores individual request metrics:
- `id`: Auto-increment primary key
- `run_id`: UUID identifying the load test run
- `timestamp`: ISO 8601 timestamp of the request
- `query_name`: Name of the PPL query executed
- `response_time_ms`: Response time in milliseconds
- `status_code`: HTTP status code
- `success`: 1 if successful, 0 if failed
- `error_message`: Error details if request failed

### `runs` Table
Stores load test run metadata:
- `run_id`: UUID primary key for the run
- `start_time`: ISO 8601 timestamp when run started
- `end_time`: ISO 8601 timestamp when run ended (NULL if still running)
- `status`: Run status ("running", "completed", etc.)
- `config_snapshot`: JSON snapshot of the configuration used for this run

## Querying Results

Example queries to analyze load test results:

```sql
-- List all runs with their duration
SELECT
  run_id,
  start_time,
  end_time,
  status,
  ROUND((julianday(end_time) - julianday(start_time)) * 86400, 2) as duration_seconds
FROM runs
ORDER BY start_time DESC;

-- Get average response times per query for a specific run
SELECT
  query_name,
  COUNT(*) as request_count,
  ROUND(AVG(response_time_ms), 2) as avg_ms,
  ROUND(MIN(response_time_ms), 2) as min_ms,
  ROUND(MAX(response_time_ms), 2) as max_ms,
  ROUND(AVG(CASE WHEN success = 1 THEN 100.0 ELSE 0.0 END), 2) as success_rate
FROM response_times
WHERE run_id = 'your-run-id-here'
GROUP BY query_name
ORDER BY avg_ms DESC;

-- Compare performance across runs
SELECT
  r.run_id,
  r.start_time,
  COUNT(rt.id) as total_requests,
  ROUND(AVG(rt.response_time_ms), 2) as avg_response_time_ms,
  ROUND(AVG(CASE WHEN rt.success = 1 THEN 100.0 ELSE 0.0 END), 2) as success_rate
FROM runs r
LEFT JOIN response_times rt ON r.run_id = rt.run_id
GROUP BY r.run_id
ORDER BY r.start_time DESC
LIMIT 10;
```
