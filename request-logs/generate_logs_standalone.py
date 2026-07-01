#!/usr/bin/env python3
# /// script
# dependencies = ["faker>=30.0.0"]
# ///
"""Generate 50M records for PPL analytics/extraction testing.

Inlines minimal request-logs logic + adds JSON-in-string, syslog format, arrays, nested objects.
Streams ndjson to stdout — pipe to `zstd -T0 -10 > documents-ppl.json.zst`.
"""
import sys
import json
import random
import uuid
from datetime import datetime, timezone, timedelta

from faker import Faker

RECORD_COUNT = 50_000_000


# Dimension pools (static, varied cardinality)
HOSTS = []
ENDPOINTS = []
CLIENTS = []
HTTP_STATUSES = [
    (200, "OK", True),
    (201, "Created", True),
    (204, "No Content", True),
    (400, "Bad Request", False),
    (401, "Unauthorized", False),
    (403, "Forbidden", False),
    (404, "Not Found", False),
    (429, "Too Many Requests", False),
    (500, "Internal Server Error", False),
    (502, "Bad Gateway", False),
    (503, "Service Unavailable", False),
    (504, "Gateway Timeout", False),
]


def init_pools(fake: Faker):
    """Pre-populate dimension pools."""
    environments = ["prod", "staging", "dev"]
    regions = ["us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-1"]
    instance_types = ["t3.large", "t3.xlarge", "c5.xlarge", "c5.2xlarge", "m5.large"]
    services = [
        "auth-service",
        "user-service",
        "order-service",
        "payment-service",
        "inventory-service",
        "notification-service",
    ]
    os_options = ["Amazon Linux 2", "Ubuntu 20.04", "Ubuntu 22.04"]

    # 300 hosts (low cardinality)
    for _ in range(300):
        region = random.choice(regions)
        service_name = random.choice(services)
        environment = random.choices(environments, weights=[70, 20, 10])[0]
        HOSTS.append(
            {
                "host_id": f"i-{fake.hexify(text='^^^^^^^^^^^^^^^^', upper=False)}",
                "host_name": f"{service_name}-{environment}-{fake.lexify(text='????').lower()}",
                "environment": environment,
                "region": region,
                "availability_zone": f"{region}{random.choice(['a', 'b', 'c'])}",
                "instance_type": random.choice(instance_types),
                "operating_system": random.choice(os_options),
                "service_name": service_name,
                "service_version": f"{random.randint(1, 3)}.{random.randint(0, 20)}.{random.randint(0, 10)}",
            }
        )

    # 3000 endpoints (medium cardinality)
    methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
    resources = [
        "users",
        "orders",
        "products",
        "payments",
        "sessions",
        "notifications",
        "metrics",
    ]
    api_versions = ["v1", "v2"]
    tiers = ["free", "basic", "premium", "enterprise"]

    for _ in range(3000):
        method = random.choices(methods, weights=[50, 25, 10, 10, 5])[0]
        resource = random.choice(resources)
        api_version = random.choices(api_versions, weights=[30, 70])[0]
        patterns = [
            f"/api/{api_version}/{resource}",
            f"/api/{api_version}/{resource}/{{id}}",
            f"/api/{api_version}/{resource}/{{id}}/details",
            f"/api/{api_version}/{resource}/search",
        ]
        ENDPOINTS.append(
            {
                "http_method": method,
                "endpoint_path": random.choice(patterns),
                "api_version": api_version,
                "resource_type": resource,
                "is_authenticated": random.random() > 0.2,
                "rate_limit_tier": random.choice(tiers),
            }
        )

    # 30000 clients (high cardinality)
    countries = [
        "United States",
        "United Kingdom",
        "Germany",
        "France",
        "Japan",
        "Brazil",
        "Canada",
        "Australia",
    ]
    browsers = ["Chrome", "Firefox", "Safari", "Edge", "curl", "Python-requests"]
    devices = ["Desktop", "Mobile", "Tablet", "Server"]
    os_families = ["Windows", "macOS", "Linux", "iOS", "Android"]

    for _ in range(30000):
        is_bot = random.random() < 0.15
        device_type = "Server" if is_bot else random.choice(devices)
        user_agent = "Bot" if is_bot else random.choice(browsers)
        CLIENTS.append(
            {
                "client_ip_hash": fake.sha256(),
                "client_country": random.choices(
                    countries, weights=[40, 15, 10, 8, 10, 5, 7, 5]
                )[0],
                "client_region": fake.state(),
                "client_city": fake.city(),
                "client_isp": fake.company(),
                "user_agent_family": user_agent,
                "user_agent_version": f"{random.randint(90, 120)}.0.{random.randint(1000, 9999)}",
                "device_type": device_type,
                "os_family": random.choice(os_families),
                "is_bot": is_bot,
                "api_client_id": (
                    f"client_{fake.uuid4()}" if random.random() > 0.5 else None
                ),
            }
        )


def generate_fact(fake: Faker) -> dict:
    """Generate one fact with analytics + extraction fields."""
    host = random.choice(HOSTS)
    endpoint = random.choice(ENDPOINTS)
    client = random.choice(CLIENTS)
    status_code, status_text, is_success = random.choices(
        HTTP_STATUSES, weights=[85, 3, 2, 2, 1, 1, 2, 1, 1, 1, 0.5, 0.5]
    )[0]

    base_latency = 50.0 * random.uniform(0.8, 2.0)
    latency_ms = int(
        max(
            5,
            random.gauss(
                base_latency if is_success else base_latency * 4, base_latency * 0.4
            ),
        )
    )
    time_to_first_byte = int(latency_ms * random.uniform(0.3, 0.6))
    upstream_latency = int(latency_ms * random.uniform(0.5, 0.8))

    request_body_size = (
        random.randint(100, 50000)
        if endpoint["http_method"] in ["POST", "PUT", "PATCH"]
        else 0
    )
    response_body_size = (
        random.randint(200, 100000) if is_success else random.randint(50, 500)
    )
    bytes_sent = response_body_size + random.randint(100, 500)
    bytes_received = request_body_size + random.randint(100, 300)

    is_error = not is_success
    retry_count = random.randint(1, 3) if is_error and random.random() < 0.3 else 0

    # Spread timestamps over last year
    now = datetime.now(timezone.utc)
    timestamp = now - timedelta(seconds=random.randint(0, 365 * 24 * 3600))
    ts_iso = timestamp.isoformat().replace("+00:00", "Z")
    request_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())

    # Base fact
    fact = {
        "request_id": request_id,
        "trace_id": trace_id,
        "@timestamp": ts_iso,
        "request_timestamp": ts_iso,
        "latency_ms": latency_ms,
        "time_to_first_byte_ms": time_to_first_byte,
        "upstream_latency_ms": upstream_latency,
        "bytes_sent": bytes_sent,
        "bytes_received": bytes_received,
        "request_body_size": request_body_size,
        "response_body_size": response_body_size,
        "request_count": 1,
        "is_error": 1 if is_error else 0,
        "is_timeout": 1 if status_code in [504, 408] else 0,
        "retry_count": retry_count,
        # Denormalized dimensions
        **host,
        **endpoint,
        **client,
        "status_code": status_code,
        "status_text": status_text,
        "year": timestamp.year,
        "quarter": (timestamp.month - 1) // 3 + 1,
        "month_name": timestamp.strftime("%B"),
        "day_name": timestamp.strftime("%A"),
        "day_of_week": timestamp.weekday() + 1,
        "is_weekend": timestamp.weekday() >= 5,
        "hour_24": timestamp.hour,
        "time_period": ["Night", "Morning", "Afternoon", "Evening", "Night"][
            (timestamp.hour // 6) % 5
        ],
        "is_business_hour": 9 <= timestamp.hour < 17,
    }

    # PPL extraction fields
    ip = f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

    # 1. raw_log: nginx-style syslog (resolve placeholders for realism)
    path = endpoint["endpoint_path"].replace("{id}", str(random.randint(1000, 999999)))
    fact["raw_log"] = (
        f"{ts_iso} nginx: {ip} - - [{ts_iso}] \"{endpoint['http_method']} {path} HTTP/1.1\" "
        f"{status_code} {bytes_sent} \"-\" \"{client['user_agent_family']}/{client['user_agent_version']}\" rt={latency_ms / 1000:.3f}"
    )

    # 2. metadata_json: stringified JSON
    metadata = {
        "trace_id": trace_id,
        "span_id": fake.uuid4(),
        "parent_span_id": fake.uuid4() if random.random() > 0.3 else None,
        "sampling_rate": random.choice([1.0, 0.1, 0.01]),
    }
    fact["metadata_json"] = json.dumps(metadata, separators=(",", ":"))

    # 3. tags: array
    tag_pool = [
        "external",
        "internal",
        "cached",
        "auth",
        "api",
        "legacy",
        "experimental",
    ]
    fact["tags"] = random.sample(tag_pool, k=random.randint(1, 4))

    # 4. headers: nested object
    fact["headers"] = {
        "content-type": random.choice(
            ["application/json", "text/html", "application/xml"]
        ),
        "x-request-id": request_id,
        "x-forwarded-for": ip,
    }
    if random.random() > 0.5:
        fact["headers"]["authorization"] = "Bearer <redacted>"

    # 5. error_details: nullable nested
    if is_error:
        fact["error_details"] = {
            "exception_type": random.choice(
                ["TimeoutError", "ConnectionError", "ValidationError", "InternalError"]
            ),
            "exception_message": fake.sentence(nb_words=8),
            "stack_trace_lines": random.randint(5, 30),
        }
    else:
        fact["error_details"] = None

    return fact


def main():
    # Parallelization: accept worker_id and total_workers as args
    worker_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    total_workers = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    chunk_size = RECORD_COUNT // total_workers
    seed = 42 + worker_id

    fake = Faker()
    Faker.seed(seed)
    random.seed(seed)

    print(
        f"# Worker {worker_id}/{total_workers}: generating {chunk_size:,} records (seed={seed})",
        file=sys.stderr,
    )
    init_pools(fake)
    print(f"# Worker {worker_id}: writing records...", file=sys.stderr)

    for i in range(chunk_size):
        fact = generate_fact(fake)
        print(json.dumps(fact, separators=(",", ":")))

        if (i + 1) % 1_000_000 == 0:
            print(f"# Worker {worker_id}: {i + 1:,} records written", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        print(f"\n# Interrupted, partial output may be usable", file=sys.stderr)
        sys.exit(0)
