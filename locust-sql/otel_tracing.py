"""OpenTelemetry tracing with file-based NDJSON export."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import Status, StatusCode


class NDJSONFileSpanExporter(SpanExporter):
    """Exports spans as NDJSON to a file."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        # Open file in append mode
        self.file = open(self.file_path, "a")

    def export(self, spans) -> SpanExportResult:
        """Export spans to NDJSON file."""
        with self.lock:
            for span in spans:
                span_dict = {
                    "trace_id": format(span.context.trace_id, "032x"),
                    "span_id": format(span.context.span_id, "016x"),
                    "parent_span_id": (
                        format(span.parent.span_id, "016x") if span.parent else None
                    ),
                    "name": span.name,
                    "start_time": self._ns_to_iso(span.start_time),
                    "end_time": self._ns_to_iso(span.end_time) if span.end_time else None,
                    "duration_ns": (
                        span.end_time - span.start_time if span.end_time else 0
                    ),
                    "duration_ms": (
                        (span.end_time - span.start_time) / 1_000_000
                        if span.end_time
                        else 0
                    ),
                    "status": {
                        "code": span.status.status_code.name,
                        "description": span.status.description,
                    },
                    "attributes": dict(span.attributes) if span.attributes else {},
                    "events": (
                        [
                            {
                                "name": event.name,
                                "timestamp": self._ns_to_iso(event.timestamp),
                                "attributes": (
                                    dict(event.attributes) if event.attributes else {}
                                ),
                            }
                            for event in span.events
                        ]
                        if span.events
                        else []
                    ),
                }
                self.file.write(json.dumps(span_dict) + "\n")
            self.file.flush()
        return SpanExportResult.SUCCESS

    def _ns_to_iso(self, timestamp_ns: int) -> str:
        """Convert nanoseconds since epoch to ISO 8601 string with nanosecond precision."""
        if not timestamp_ns:
            return None
        # Convert nanoseconds to seconds and nanoseconds remainder
        seconds = timestamp_ns // 1_000_000_000
        nanos = timestamp_ns % 1_000_000_000
        # Create datetime from seconds and format with nanoseconds
        dt = datetime.fromtimestamp(seconds, tz=UTC)
        # Format: YYYY-MM-DDTHH:MM:SS.nnnnnnnnnZ
        return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{nanos:09d}Z"

    def shutdown(self):
        """Close the file."""
        with self.lock:
            if self.file and not self.file.closed:
                self.file.close()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Flush the file."""
        with self.lock:
            if self.file and not self.file.closed:
                self.file.flush()
        return True


class OTELTracingManager:
    """Manages OTEL tracing with file-based export."""

    def __init__(self, config, run_id: str):
        self.config = config
        self.run_id = run_id
        self.tracer_provider: Optional[TracerProvider] = None
        self.exporter: Optional[NDJSONFileSpanExporter] = None
        self.tracer: Optional[trace.Tracer] = None

    def init_tracing(self):
        """Initialize OTEL tracing with file export."""
        otel_config = self.config.get("otel", {})
        if not otel_config.get("enabled", False):
            return

        # Create output directory
        output_dir = Path(otel_config.get("output_dir", "otel_output"))
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create trace file with run_id in name
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        trace_file = output_dir / f"traces_{timestamp}_{self.run_id[:8]}.ndjson"

        # Create resource with run metadata
        resource = Resource.create(
            {
                "service.name": otel_config.get("service_name", "locust-ppl-load-test"),
                "service.version": otel_config.get("service_version", "0.1.0"),
                "run.id": self.run_id,
            }
        )

        # Setup tracer provider with file exporter
        self.exporter = NDJSONFileSpanExporter(str(trace_file))
        self.tracer_provider = TracerProvider(resource=resource)
        self.tracer_provider.add_span_processor(
            # Use simple span processor for immediate writes (no batching)
            SimpleSpanProcessor(self.exporter)
        )

        # Set as global tracer provider
        trace.set_tracer_provider(self.tracer_provider)

        # Get tracer
        self.tracer = trace.get_tracer("locust.ppl.load_test", "0.1.0")

        # Auto-instrument httpx for HTTP-level spans
        if otel_config.get("instrument_httpx", True):
            HTTPXClientInstrumentor().instrument()

        print(f"OTEL tracing initialized. Writing to: {trace_file}")

    def create_query_span(
        self, query_name: str, query_text: str, calcite_enabled: bool
    ):
        """Create a span for a query execution."""
        if not self.tracer:
            return None

        span = self.tracer.start_span(
            "ppl.query.execute",
            kind=trace.SpanKind.CLIENT,
            attributes={
                "query.name": query_name,
                "query.text": query_text,
                "calcite.enabled": calcite_enabled,
                "run.id": self.run_id,
            },
        )
        return span

    def record_query_response(
        self,
        span,
        status_code: int,
        response_time_ms: float,
        response_size: int,
        error: Optional[str] = None,
    ):
        """Record query response details on the span."""
        if not span:
            return

        span.set_attribute("http.status_code", status_code)
        span.set_attribute("response.time_ms", response_time_ms)
        span.set_attribute("response.size_bytes", response_size)

        if status_code == 200 and not error:
            span.set_status(Status(StatusCode.OK))
        else:
            span.set_status(Status(StatusCode.ERROR, error or f"Status {status_code}"))
            if error:
                span.record_exception(Exception(error))

    def shutdown(self):
        """Shutdown tracing and flush remaining spans."""
        if self.tracer_provider:
            self.tracer_provider.shutdown()
            print("OTEL tracing shutdown complete")
