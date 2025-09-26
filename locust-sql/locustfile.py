from locust import HttpUser, task, between
import random
from pathlib import Path


class ThreadPoolMetrics:
    def __init__(self):
        self.active = 0
        self.queue = 0
        self.rejected = 0


class OpenSearchPPLUser(HttpUser):
    queries = {}

    def on_start(self):
        if not OpenSearchPPLUser.queries:
            ppl_dir = Path("ppl")
            for ppl_file in ppl_dir.glob("*.ppl"):
                with open(ppl_file, "r") as f:
                    query = f.read().strip()
                    query_name = ppl_file.stem
                    OpenSearchPPLUser.queries[query_name] = query

    wait_time = between(1, 3)

    @task
    def execute_ppl_query(self):
        query_name = random.choice(list(self.queries.keys()))
        query = self.queries[query_name]

        payload = {"query": query}

        with self.client.post(
            "/_plugins/_ppl",
            json=payload,
            headers={"Content-Type": "application/json"},
            name=f"PPL Query: {query_name}",
            catch_response=True,
        ) as response:
            try:
                if response.status_code == 200:
                    response.success()
                else:
                    response.failure(f"Got status code {response.status_code}")
            except Exception as e:
                response.failure(f"Request failed: {str(e)}")
