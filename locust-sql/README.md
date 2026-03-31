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

[otel]
# Enable OpenTelemetry tracing (optional)
enabled = false
# Directory for OTEL output files
output_dir = "otel_output"
# Service metadata
service_name = "locust-ppl-load-test"
service_version = "0.1.0"
# Auto-instrument httpx for HTTP-level spans
instrument_httpx = true
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

#### `[otel]` (Optional)
- `enabled`: Enable OpenTelemetry distributed tracing and metrics (`true` or `false`)
- `output_dir`: Directory where trace and metric files are written (NDJSON format)
- `service_name`: Service identifier in traces
- `service_version`: Service version in traces
- `instrument_httpx`: Auto-instrument httpx for HTTP-level spans (`true` or `false`)

#### `[otel.metrics]` (Optional)
- `enabled`: Enable metrics collection (`true` or `false`)
- `interval`: Collection interval in seconds (default: 5.0)
- `collect_thread_pools`: Collect thread pool statistics (`true` or `false`)
- `collect_jvm`: Collect JVM metrics like heap memory (`true` or `false`)
- `collect_os`: Collect OS metrics like CPU, memory, disk (`true` or `false`)

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

## OpenTelemetry Tracing (Optional)

When `otel.enabled = true`, the load tester will export distributed traces to NDJSON files in the configured output directory.

### Trace File Format

Each line in `traces_*.ndjson` is a JSON object representing a completed span.

**Timestamps** are in ISO 8601 format with nanosecond precision for OpenSearch compatibility:

```json
{
  "trace_id": "1234567890abcdef1234567890abcdef",
  "span_id": "1234567890abcdef",
  "parent_span_id": null,
  "name": "ppl.query.execute",
  "start_time": "2024-03-31T17:54:04.000000000Z",
  "end_time": "2024-03-31T17:54:04.123000000Z",
  "duration_ns": 123000000,
  "duration_ms": 123.0,
  "status": {
    "code": "OK",
    "description": null
  },
  "attributes": {
    "query.name": "search_with_aggregation",
    "query.text": "source=logs | stats count() by level",
    "calcite.enabled": true,
    "run.id": "uuid-of-run",
    "http.status_code": 200,
    "response.time_ms": 123.45,
    "response.size_bytes": 1234
  },
  "events": [
    {"name": "query.sent", "timestamp": "2024-03-31T17:54:04.001000000Z", "attributes": {}},
    {"name": "query.completed", "timestamp": "2024-03-31T17:54:04.123000000Z", "attributes": {}}
  ]
}
```

### Analyzing Traces

You can use standard command-line tools to analyze traces:

```bash
# Find slow queries
jq 'select(.duration_ms > 500)' otel_output/traces_*.ndjson

# Get average latency per query
jq -r '[.attributes."query.name", .duration_ms] | @tsv' otel_output/traces_*.ndjson | \
  awk '{sum[$1]+=$2; count[$1]++} END {for(q in sum) print q, sum[q]/count[q]}' | \
  sort -k2 -rn

# Find all errors
jq 'select(.status.code == "ERROR")' otel_output/traces_*.ndjson

# Get P95 latency
jq -r '.duration_ms' otel_output/traces_*.ndjson | sort -n | awk '{a[NR]=$0} END {print a[int(NR*0.95)]}'
```

### Metrics Collection

When `otel.metrics.enabled = true`, the load tester collects cluster metrics in the background and exports them to `metrics_*.ndjson`.

#### Metrics File Format

Each line is a single metric reading:

```json
{
  "timestamp": "2026-03-31T10:15:30.123456Z",
  "metric": "opensearch.threadpool.active",
  "value": 5,
  "labels": {
    "node": "opensearch-node-1",
    "pool": "sql-worker",
    "run_id": "uuid-of-run"
  }
}
```

#### Collected Metrics

**Thread Pool Metrics:**
- `opensearch.threadpool.active` - Active threads in pool
- `opensearch.threadpool.queue` - Queued tasks
- `opensearch.threadpool.rejected` - Rejected tasks

**JVM Metrics:**
- `opensearch.jvm.heap.used_bytes` - Heap memory used
- `opensearch.jvm.heap.max_bytes` - Maximum heap memory
- `opensearch.jvm.heap.percent` - Heap utilization percentage

**OS Metrics:**
- `opensearch.os.cpu.percent` - CPU usage percentage
- `opensearch.os.mem.used_bytes` - OS memory used
- `opensearch.os.mem.total_bytes` - Total OS memory
- `opensearch.os.mem.percent` - Memory utilization percentage

**Disk Metrics:**
- `opensearch.fs.total_bytes` - Total disk space
- `opensearch.fs.available_bytes` - Available disk space
- `opensearch.fs.percent` - Disk utilization percentage

#### Analyzing Metrics

```bash
# Get average CPU usage
jq -r 'select(.metric == "opensearch.os.cpu.percent") | .value' otel_output/metrics_*.ndjson | \
  awk '{sum+=$1; count++} END {print sum/count}'

# Find SQL thread pool queue spikes
jq 'select(.metric == "opensearch.threadpool.queue" and .labels.pool | contains("sql")) | select(.value > 10)' \
  otel_output/metrics_*.ndjson

# Track heap usage over time
jq -r 'select(.metric == "opensearch.jvm.heap.percent") | [.timestamp, .labels.node, .value] | @tsv' \
  otel_output/metrics_*.ndjson

# Get thread pool stats for a specific pool
jq 'select(.labels.pool == "sql-worker")' otel_output/metrics_*.ndjson | \
  jq -s 'group_by(.metric) | map({metric: .[0].metric, avg: (map(.value) | add / length)})'
```

### Ingesting to Observability Backends

The NDJSON format can be directly ingested into various backends:

**OpenSearch/Elasticsearch:**
```bash
# Bulk ingest traces
cat otel_output/traces_*.ndjson | \
  jq -c '. as $doc | {"index": {}}, $doc' | \
  curl -X POST "localhost:9200/traces/_bulk" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @-

# Bulk ingest metrics
cat otel_output/metrics_*.ndjson | \
  jq -c '. as $doc | {"index": {}}, $doc' | \
  curl -X POST "localhost:9200/metrics/_bulk" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @-
```

**Other backends:**
- **Jaeger**: Convert to Jaeger JSON format and import
- **Grafana Tempo**: Use the traces API to push spans
- **Prometheus**: Convert metrics to Prometheus exposition format
- **Custom analysis**: Process with Python/pandas for custom analytics
```
