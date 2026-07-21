import random
import threading
from pathlib import Path

from locust import HttpUser, between, events, task
from opentelemetry import trace

from database import DatabaseManager, load_config
from otel_tracing import OTELTracingManager
from otel_metrics import ClusterMetricsCollector

# Global configuration and database manager
CONFIG = load_config()
db_manager = DatabaseManager(CONFIG)

# Slow query throttling
slow_query_counter = 0
slow_query_lock = threading.Lock()
SLOW_QUERY_LIMIT = CONFIG.get("throttle", {}).get("limit", 0)  # 0 = disabled
SLOW_QUERY_PATTERN = CONFIG.get("throttle", {}).get("pattern", None)

# OTEL tracing manager (if enabled)
otel_manager = OTELTracingManager(CONFIG, db_manager.run_id)
otel_manager.init_tracing()

# OTEL metrics collector (if enabled)
metrics_collector: ClusterMetricsCollector = None
metrics_collector_started = False


def record_response(
    request_type, name, response_time, response_length, exception, **kwargs
):
    """Event handler to record each request's response time to the database."""
    # Extract query name from the name field (format: "PPL Query: {query_name}")
    query_name = (
        name.replace("PPL Query: ", "") if name.startswith("PPL Query: ") else name
    )

    # Determine success and error info
    success = 1 if exception is None else 0
    status_code = None
    error_message = None

    if hasattr(kwargs.get("response"), "status_code"):
        status_code = kwargs["response"].status_code

    if exception:
        error_message = str(exception)

    db_manager.record_response(
        query_name, response_time, status_code, success, error_message
    )


# Register event handlers
events.request.add_listener(record_response)


@events.quitting.add_listener
def on_quitting(_environment, **_kwargs):
    """Handle locust shutdown to mark run as completed."""
    db_manager.flush_remaining()
    db_manager.end_run("completed")
    otel_manager.shutdown()
    if metrics_collector:
        metrics_collector.shutdown()


# Initialize database and start run tracking
db_manager.init_database()
db_manager.start_run()


class ThreadPoolMetrics:
    def __init__(self):
        self.active = 0
        self.queue = 0
        self.rejected = 0


class OpenSearchPPLUser(HttpUser):
    queries = {}
    slow_queries = {}
    fast_queries = {}
    host = CONFIG["opensearch"]["url"]

    def on_start(self):
        """Initialize user session: load queries and configure cluster settings."""
        self._setup_auth()
        self._load_ppl_queries()
        self._configure_calcite()
        self._start_metrics_collector()

    def _setup_auth(self):
        """Configure HTTP basic auth if credentials are provided."""
        username = CONFIG["opensearch"].get("username", "")
        password = CONFIG["opensearch"].get("password", "")
        if username and password:
            self.client.auth = (username, password)

    def _load_ppl_queries(self):
        """Load PPL query files from configured directory with exclusion patterns."""
        if OpenSearchPPLUser.queries:
            return  # Already loaded by another user

        ppl_dir = Path(CONFIG["tests"]["ppl_directory"])
        exclude_patterns = CONFIG["tests"]["exclude_patterns"]

        for ppl_file in ppl_dir.glob("*.ppl"):
            query_name = ppl_file.stem

            # Skip if query name matches any exclusion pattern
            if any(pattern in query_name for pattern in exclude_patterns):
                continue

            with open(ppl_file, "r") as f:
                query = (
                    f.read().strip().replace("source = big5", "source = big5_parquet")
                )
                query = self._inject_time_filter(query)
                OpenSearchPPLUser.queries[query_name] = query

                # Categorize as slow or fast based on pattern
                if SLOW_QUERY_PATTERN and query_name.startswith(SLOW_QUERY_PATTERN):
                    OpenSearchPPLUser.slow_queries[query_name] = query
                else:
                    OpenSearchPPLUser.fast_queries[query_name] = query

        print(f"Loaded {len(OpenSearchPPLUser.queries)} PPL queries from {ppl_dir}")
        if SLOW_QUERY_LIMIT:
            print(
                f"  {len(OpenSearchPPLUser.slow_queries)} slow (pattern: {SLOW_QUERY_PATTERN}), {len(OpenSearchPPLUser.fast_queries)} fast, limit: {SLOW_QUERY_LIMIT}"
            )

    def _inject_time_filter(self, query):
        """Inject time filter after source clause if time_range is configured."""
        import re

        if "time_range" not in CONFIG:
            return query

        start = CONFIG["time_range"]["start"]
        end = CONFIG["time_range"]["end"]
        time_filter = f'`@timestamp` >= "{start}" AND `@timestamp` <= "{end}"'

        # Replace source=idx with source=idx | where <time_filter>
        return re.sub(
            r"(source\s*=\s*\w+)", rf"\1 | where {time_filter}", query, count=1
        )

    def _get_cluster_calcite_setting(self):
        """Retrieve the current Calcite plugin setting from the cluster."""
        response = self.client.get("/_cluster/settings", catch_response=True)
        if response.status_code != 200:
            raise Exception(f"Failed to get cluster settings: {response.status_code}")

        settings = response.json()
        return (
            settings.get("transient", {})
            .get("plugins", {})
            .get("calcite", {})
            .get("enabled", "true")
        )

    def _update_cluster_calcite_setting(self, expected_value):
        """Update the Calcite plugin setting in the cluster."""
        update_response = self.client.put(
            "/_cluster/settings",
            json={"transient": {"plugins.calcite.enabled": expected_value}},
            catch_response=True,
        )
        if update_response.status_code != 200:
            raise Exception(
                f"Failed to update Calcite setting: {update_response.status_code} - {update_response.text}"
            )
        print(f"Successfully updated Calcite setting to '{expected_value}'")

    def _configure_calcite(self):
        """Configure or validate Calcite plugin setting based on config."""
        calcite_enabled = CONFIG["calcite"]["enabled"]
        enforce_calcite = CONFIG["calcite"]["enforce"]
        expected_value = "true" if calcite_enabled else "false"

        current_value = self._get_cluster_calcite_setting()

        if current_value == expected_value:
            return  # Settings match, nothing to do

        if enforce_calcite:
            # Update the cluster setting to match config
            print(
                f"Updating Calcite setting from '{current_value}' to '{expected_value}'"
            )
            self._update_cluster_calcite_setting(expected_value)
        else:
            # Only check, don't enforce
            raise AssertionError(
                f"Calcite plugin setting mismatch: expected '{expected_value}', got '{current_value}'. "
                f"Set calcite.enforce = true in config.toml to auto-update."
            )

    def _start_metrics_collector(self):
        """Start the metrics collector (only once, from first user)."""
        global metrics_collector, metrics_collector_started

        if metrics_collector_started:
            return

        metrics_collector_started = True
        metrics_collector = ClusterMetricsCollector(
            self.client, CONFIG, db_manager.run_id
        )
        metrics_collector.init_metrics()
        metrics_collector.start()

    wait_time = between(1, 3)

    def _select_random_query(self):
        """Select a query, respecting slow query limit if configured."""
        global slow_query_counter

        if not SLOW_QUERY_LIMIT:
            # Throttle disabled, pick any
            query_name = random.choice(list(self.queries.keys()))
            return query_name, self.queries[query_name], False

        # Optimistically claim slot
        with slow_query_lock:
            slow_query_counter += 1
            current = slow_query_counter

        # Check if over limit or no slow queries
        if current > SLOW_QUERY_LIMIT or not self.slow_queries:
            with slow_query_lock:
                slow_query_counter -= 1
            # Use fast query
            if self.fast_queries:
                query_name = random.choice(list(self.fast_queries.keys()))
                return query_name, self.fast_queries[query_name], False
            # No fast available, use slow but uncounted
            query_name = random.choice(list(self.slow_queries.keys()))
            return query_name, self.slow_queries[query_name], False

        # Under limit, proceed with slow (already counted)
        query_name = random.choice(list(self.slow_queries.keys()))
        return query_name, self.slow_queries[query_name], True

    def _parse_error_response(self, response):
        """Parse error response and extract meaningful error message."""
        error_msg = f"Status {response.status_code}"

        try:
            error_body = response.json()
            if "error" in error_body:
                err = error_body["error"]
                if isinstance(err, dict):
                    # Extract structured error fields
                    parts = []
                    if reason := err.get("reason", ""):
                        parts.append(reason)
                    if error_type := err.get("type", ""):
                        parts.append(f"[{error_type}]")
                    if details := err.get("details", ""):
                        parts.append(details)

                    if parts:
                        error_msg += ": " + " - ".join(parts)
                else:
                    error_msg += f": {err}"
            else:
                error_msg += f": {error_body}"
        except Exception:
            error_msg += f": {response.text}"

        return error_msg

    def _handle_response(self, response):
        """Handle and validate PPL query response."""
        if response.status_code == 200:
            response.success()
        else:
            error_msg = self._parse_error_response(response)
            response.failure(error_msg)

    @task
    def execute_ppl_query(self):
        """Execute a random PPL query against the cluster."""
        global slow_query_counter

        query_name, query, is_slow = self._select_random_query()

        try:
            # Create OTEL span for this query
            span = otel_manager.create_query_span(
                query_name, query, CONFIG["calcite"]["enabled"]
            )

            with self.client.post(
                "/_plugins/_ppl",
                json={"query": query},
                headers={"Content-Type": "application/json"},
                name=f"PPL Query: {query_name}",
                catch_response=True,
            ) as response:
                try:
                    if span:
                        span.add_event("query.sent")

                    self._handle_response(response)

                    # Record response details on span
                    if span:
                        response_time_ms = response.elapsed.total_seconds() * 1000
                        response_size = len(response.content) if response.content else 0
                        error_msg = (
                            None
                            if response.status_code == 200
                            else self._parse_error_response(response)
                        )

                        otel_manager.record_query_response(
                            span,
                            response.status_code,
                            response_time_ms,
                            response_size,
                            error_msg,
                        )
                        span.add_event("query.completed")

                except Exception as e:
                    if span:
                        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                    response.failure(f"Request failed: {str(e)}")
                finally:
                    if span:
                        span.end()
        finally:
            if is_slow:
                with slow_query_lock:
                    slow_query_counter -= 1
