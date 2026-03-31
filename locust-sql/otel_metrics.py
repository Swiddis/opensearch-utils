"""OpenTelemetry metrics collection with file-based NDJSON export."""

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional


class NDJSONFileMetricsExporter:
    """Exports metrics as NDJSON to a file."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.file = open(self.file_path, "a")

    def export(self, metric_name: str, value: float, labels: dict, timestamp: Optional[datetime] = None):
        """Export a single metric reading."""
        if timestamp is None:
            timestamp = datetime.now(UTC)

        metric_dict = {
            "timestamp": timestamp.isoformat(),
            "metric": metric_name,
            "value": value,
            "labels": labels,
        }

        with self.lock:
            self.file.write(json.dumps(metric_dict) + "\n")
            self.file.flush()

    def shutdown(self):
        """Close the file."""
        with self.lock:
            if self.file and not self.file.closed:
                self.file.close()


class ClusterMetricsCollector:
    """Collects OpenSearch cluster metrics in a background thread."""

    def __init__(self, client, config, run_id: str):
        self.client = client
        self.config = config
        self.run_id = run_id
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.exporter: Optional[NDJSONFileMetricsExporter] = None

        metrics_config = config.get("otel", {}).get("metrics", {})
        self.interval = metrics_config.get("interval", 5.0)
        self.collect_thread_pools = metrics_config.get("collect_thread_pools", True)
        self.collect_jvm = metrics_config.get("collect_jvm", True)
        self.collect_os = metrics_config.get("collect_os", True)

    def init_metrics(self):
        """Initialize metrics collection."""
        otel_config = self.config.get("otel", {})
        if not otel_config.get("enabled", False):
            return

        metrics_config = otel_config.get("metrics", {})
        if not metrics_config.get("enabled", True):
            return

        # Create output directory
        output_dir = Path(otel_config.get("output_dir", "otel_output"))
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create metrics file with run_id in name
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        metrics_file = output_dir / f"metrics_{timestamp}_{self.run_id[:8]}.ndjson"

        # Setup exporter
        self.exporter = NDJSONFileMetricsExporter(str(metrics_file))

        print(f"OTEL metrics initialized. Writing to: {metrics_file}")

    def start(self):
        """Start the background metrics collection thread."""
        if not self.exporter:
            return

        self.running = True
        self.thread = threading.Thread(target=self._collect_loop, daemon=True)
        self.thread.start()
        print(f"Metrics collection started (interval: {self.interval}s)")

    def _collect_loop(self):
        """Main collection loop that runs in background thread."""
        while self.running:
            try:
                timestamp = datetime.now(UTC)

                if self.collect_thread_pools:
                    self._collect_thread_pools(timestamp)

                if self.collect_jvm or self.collect_os:
                    self._collect_node_stats(timestamp)

            except Exception as e:
                print(f"Error collecting metrics: {e}")

            # Sleep until next collection
            time.sleep(self.interval)

    def _collect_thread_pools(self, timestamp: datetime):
        """Collect thread pool statistics from _cat/thread_pool."""
        try:
            response = self.client.get("/_cat/thread_pool?format=json&h=node_name,name,active,queue,rejected")
            if response.status_code != 200:
                return

            for pool in response.json():
                node_name = pool.get("node_name", "unknown")
                pool_name = pool.get("name", "unknown")

                labels = {
                    "node": node_name,
                    "pool": pool_name,
                    "run_id": self.run_id,
                }

                # Export active threads
                active = int(pool.get("active", 0))
                self.exporter.export(
                    "opensearch.threadpool.active",
                    active,
                    labels,
                    timestamp,
                )

                # Export queue size
                queue = int(pool.get("queue", 0))
                self.exporter.export(
                    "opensearch.threadpool.queue",
                    queue,
                    labels,
                    timestamp,
                )

                # Export rejected count
                rejected = int(pool.get("rejected", 0))
                self.exporter.export(
                    "opensearch.threadpool.rejected",
                    rejected,
                    labels,
                    timestamp,
                )

        except Exception as e:
            print(f"Error collecting thread pool stats: {e}")

    def _collect_node_stats(self, timestamp: datetime):
        """Collect node statistics from _nodes/stats."""
        try:
            # Request only the stats we need
            stats_filter = []
            if self.collect_jvm:
                stats_filter.append("jvm")
            if self.collect_os:
                stats_filter.append("os")
                stats_filter.append("fs")

            response = self.client.get(f"/_nodes/stats/{','.join(stats_filter)}")
            if response.status_code != 200:
                return

            data = response.json()
            for node_id, node in data.get("nodes", {}).items():
                node_name = node.get("name", "unknown")

                base_labels = {
                    "node": node_name,
                    "node_id": node_id,
                    "run_id": self.run_id,
                }

                # JVM metrics
                if self.collect_jvm and "jvm" in node:
                    self._export_jvm_metrics(node["jvm"], base_labels, timestamp)

                # OS metrics
                if self.collect_os and "os" in node:
                    self._export_os_metrics(node["os"], base_labels, timestamp)

                # Filesystem metrics (disk)
                if self.collect_os and "fs" in node:
                    self._export_fs_metrics(node["fs"], base_labels, timestamp)

        except Exception as e:
            print(f"Error collecting node stats: {e}")

    def _export_jvm_metrics(self, jvm: dict, labels: dict, timestamp: datetime):
        """Export JVM memory metrics."""
        mem = jvm.get("mem", {})

        # Heap memory
        heap_used = mem.get("heap_used_in_bytes")
        if heap_used is not None:
            self.exporter.export(
                "opensearch.jvm.heap.used_bytes",
                heap_used,
                labels | {"memory_type": "heap"},
                timestamp,
            )

        heap_max = mem.get("heap_max_in_bytes")
        if heap_max is not None:
            self.exporter.export(
                "opensearch.jvm.heap.max_bytes",
                heap_max,
                labels | {"memory_type": "heap"},
                timestamp,
            )

        # Heap utilization percentage
        if heap_used is not None and heap_max is not None and heap_max > 0:
            heap_percent = (heap_used / heap_max) * 100
            self.exporter.export(
                "opensearch.jvm.heap.percent",
                heap_percent,
                labels,
                timestamp,
            )

    def _export_os_metrics(self, os_stats: dict, labels: dict, timestamp: datetime):
        """Export OS metrics (CPU)."""
        # CPU percentage
        cpu = os_stats.get("cpu", {})
        cpu_percent = cpu.get("percent")
        if cpu_percent is not None:
            self.exporter.export(
                "opensearch.os.cpu.percent",
                cpu_percent,
                labels,
                timestamp,
            )

        # Memory
        mem = os_stats.get("mem", {})
        mem_used = mem.get("used_in_bytes")
        if mem_used is not None:
            self.exporter.export(
                "opensearch.os.mem.used_bytes",
                mem_used,
                labels,
                timestamp,
            )

        mem_free = mem.get("free_in_bytes")
        if mem_free is not None:
            self.exporter.export(
                "opensearch.os.mem.free_bytes",
                mem_free,
                labels,
                timestamp,
            )

        mem_total = mem.get("total_in_bytes")
        if mem_total is not None:
            self.exporter.export(
                "opensearch.os.mem.total_bytes",
                mem_total,
                labels,
                timestamp,
            )

            # Memory utilization percentage
            if mem_used is not None and mem_total > 0:
                mem_percent = (mem_used / mem_total) * 100
                self.exporter.export(
                    "opensearch.os.mem.percent",
                    mem_percent,
                    labels,
                    timestamp,
                )

    def _export_fs_metrics(self, fs: dict, labels: dict, timestamp: datetime):
        """Export filesystem (disk) metrics."""
        total = fs.get("total", {})

        # Total disk space
        total_bytes = total.get("total_in_bytes")
        if total_bytes is not None:
            self.exporter.export(
                "opensearch.fs.total_bytes",
                total_bytes,
                labels,
                timestamp,
            )

        # Available disk space
        available_bytes = total.get("available_in_bytes")
        if available_bytes is not None:
            self.exporter.export(
                "opensearch.fs.available_bytes",
                available_bytes,
                labels,
                timestamp,
            )

        # Free disk space
        free_bytes = total.get("free_in_bytes")
        if free_bytes is not None:
            self.exporter.export(
                "opensearch.fs.free_bytes",
                free_bytes,
                labels,
                timestamp,
            )

        # Disk utilization percentage
        if total_bytes is not None and available_bytes is not None and total_bytes > 0:
            used_bytes = total_bytes - available_bytes
            disk_percent = (used_bytes / total_bytes) * 100
            self.exporter.export(
                "opensearch.fs.percent",
                disk_percent,
                labels,
                timestamp,
            )

    def shutdown(self):
        """Stop metrics collection and close file."""
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join(timeout=10.0)
            print("Metrics collection stopped")

        if self.exporter:
            self.exporter.shutdown()
            print("Metrics export shutdown complete")
