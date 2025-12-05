import random
from pathlib import Path

from locust import HttpUser, between, events, task

from database import DatabaseManager, load_config

# Global configuration and database manager
CONFIG = load_config()
db_manager = DatabaseManager(CONFIG)


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
    db_manager.end_run("completed")


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

    def on_start(self):
        """Initialize user session: load queries and configure cluster settings."""
        self._load_ppl_queries()
        self._configure_calcite()

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
                query = f.read().strip()
                OpenSearchPPLUser.queries[query_name] = query

        print(f"Loaded {len(OpenSearchPPLUser.queries)} PPL queries from {ppl_dir}")

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

    wait_time = between(1, 3)

    def _select_random_query(self):
        """Select a random query from the loaded queries."""
        query_name = random.choice(list(self.queries.keys()))
        return query_name, self.queries[query_name]

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
        query_name, query = self._select_random_query()

        with self.client.post(
            "/_plugins/_ppl",
            json={"query": query},
            headers={"Content-Type": "application/json"},
            name=f"PPL Query: {query_name}",
            catch_response=True,
        ) as response:
            try:
                self._handle_response(response)
            except Exception as e:
                response.failure(f"Request failed: {str(e)}")
