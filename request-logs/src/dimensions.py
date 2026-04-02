"""
Dimension tables for Kimball-style dimensional modeling.
Manages dimension data with realistic reuse patterns.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Dict, Any, Optional
import random
import uuid
from faker import Faker


@dataclass
class DimHost:
    """Host dimension (Type 2 SCD)"""
    host_key: str
    host_id: str
    host_name: str
    environment: str
    region: str
    availability_zone: str
    datacenter: str
    instance_type: str
    operating_system: str
    service_name: str
    service_version: str
    cluster_name: str
    effective_date: str
    expiration_date: Optional[str]
    is_current: bool


@dataclass
class DimEndpoint:
    """API endpoint dimension"""
    endpoint_key: str
    http_method: str
    endpoint_path: str
    endpoint_pattern: str
    api_version: str
    resource_type: str
    is_authenticated: bool
    rate_limit_tier: str


@dataclass
class DimHttpStatus:
    """HTTP status code dimension"""
    status_key: str
    status_code: int
    status_text: str
    status_category: str
    is_success: bool
    is_client_error: bool
    is_server_error: bool


@dataclass
class DimClient:
    """Client/user-agent dimension"""
    client_key: str
    client_ip_hash: str
    client_country: str
    client_region: str
    client_city: str
    client_isp: str
    user_agent_family: str
    user_agent_version: str
    device_type: str
    os_family: str
    is_bot: bool
    api_client_id: Optional[str]


@dataclass
class DimDate:
    """Date dimension"""
    date_key: str
    full_date: str
    day_of_week: int
    day_name: str
    day_of_month: int
    day_of_year: int
    week_of_year: int
    month_number: int
    month_name: str
    quarter: int
    year: int
    is_weekend: bool
    is_holiday: bool
    fiscal_quarter: int
    fiscal_year: int


@dataclass
class DimTimeOfDay:
    """Time of day dimension"""
    time_key: str
    full_time: str
    hour_24: int
    hour_12: int
    minute: int
    second: int
    am_pm: str
    time_period: str
    is_business_hour: bool
    hour_bucket: str


class DimensionManager:
    """Manages all dimensions with realistic reuse patterns"""

    def __init__(self, seed: int | None = None, grow: bool = True):
        self.fake = Faker()
        Faker.seed(seed)
        random.seed(seed)
        self.grow = grow

        # Dimension storage
        self.hosts: List[DimHost] = []
        self.endpoints: List[DimEndpoint] = []
        self.http_statuses: List[DimHttpStatus] = []
        self.clients: List[DimClient] = []
        self.dates: Dict[int, DimDate] = {}
        self.times: Dict[int, DimTimeOfDay] = {}

        # Initialize static dimensions
        self._initialize_http_statuses()
        self._initialize_times()

    def _initialize_http_statuses(self):
        """Initialize all common HTTP status codes"""
        statuses = [
            (200, "OK", "Success", True, False, False),
            (201, "Created", "Success", True, False, False),
            (204, "No Content", "Success", True, False, False),
            (301, "Moved Permanently", "Redirection", False, False, False),
            (302, "Found", "Redirection", False, False, False),
            (304, "Not Modified", "Redirection", False, False, False),
            (400, "Bad Request", "Client Error", False, True, False),
            (401, "Unauthorized", "Client Error", False, True, False),
            (403, "Forbidden", "Client Error", False, True, False),
            (404, "Not Found", "Client Error", False, True, False),
            (429, "Too Many Requests", "Client Error", False, True, False),
            (500, "Internal Server Error", "Server Error", False, False, True),
            (502, "Bad Gateway", "Server Error", False, False, True),
            (503, "Service Unavailable", "Server Error", False, False, True),
            (504, "Gateway Timeout", "Server Error", False, False, True),
        ]

        for idx, (code, text, category, success, client_err, server_err) in enumerate(statuses):
            self.http_statuses.append(
                DimHttpStatus(
                    status_key=str(uuid.uuid4()),
                    status_code=code,
                    status_text=text,
                    status_category=category,
                    is_success=success,
                    is_client_error=client_err,
                    is_server_error=server_err,
                )
            )

    def _initialize_times(self):
        """Initialize all time of day records (hourly granularity)"""
        for hour in range(24):
            for minute in [0, 15, 30, 45]:  # 15-minute buckets
                time_key = hour * 10000 + minute * 100
                hour_12 = hour % 12 if hour % 12 != 0 else 12
                am_pm = "AM" if hour < 12 else "PM"

                if 6 <= hour < 12:
                    period = "Morning"
                elif 12 <= hour < 17:
                    period = "Afternoon"
                elif 17 <= hour < 21:
                    period = "Evening"
                else:
                    period = "Night"

                hour_bucket = f"{hour:02d}:00-{hour:02d}:59"
                is_business = 9 <= hour < 17

                self.times[time_key] = DimTimeOfDay(
                    time_key=str(uuid.uuid4()),
                    full_time=f"{hour:02d}:{minute:02d}:00",
                    hour_24=hour,
                    hour_12=hour_12,
                    minute=minute,
                    second=0,
                    am_pm=am_pm,
                    time_period=period,
                    is_business_hour=is_business,
                    hour_bucket=hour_bucket,
                )

    def get_or_create_date(self, dt: datetime) -> DimDate:
        """Get or create date dimension for a given datetime"""
        date_key = int(dt.strftime("%Y%m%d"))

        if date_key in self.dates:
            return self.dates[date_key]

        day_name = dt.strftime("%A")
        month_name = dt.strftime("%B")

        # Simple fiscal year: starts in October
        fiscal_quarter = ((dt.month - 1 + 3) % 12) // 3 + 1
        fiscal_year = dt.year if dt.month >= 10 else dt.year - 1

        dim_date = DimDate(
            date_key=str(uuid.uuid4()),
            full_date=dt.strftime("%Y-%m-%d"),
            day_of_week=dt.weekday() + 1,
            day_name=day_name,
            day_of_month=dt.day,
            day_of_year=dt.timetuple().tm_yday,
            week_of_year=dt.isocalendar()[1],
            month_number=dt.month,
            month_name=month_name,
            quarter=(dt.month - 1) // 3 + 1,
            year=dt.year,
            is_weekend=dt.weekday() >= 5,
            is_holiday=False,  # Simplified
            fiscal_quarter=fiscal_quarter,
            fiscal_year=fiscal_year,
        )

        self.dates[date_key] = dim_date
        return dim_date

    def get_time(self, dt: datetime) -> DimTimeOfDay:
        """Get time dimension for a given datetime (rounds to 15-min bucket)"""
        minute_bucket = (dt.minute // 15) * 15
        time_key = dt.hour * 10000 + minute_bucket * 100
        return self.times[time_key]

    def create_host(self) -> DimHost:
        """Create a new host dimension record"""
        environments = ["prod", "staging", "dev"]
        regions = ["us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-1"]
        instance_types = ["t3.large", "t3.xlarge", "c5.xlarge", "c5.2xlarge", "m5.large", "m5.xlarge"]
        os_options = ["Amazon Linux 2", "Ubuntu 20.04", "Ubuntu 22.04", "CentOS 7"]
        services = ["auth-service", "user-service", "order-service", "payment-service", "inventory-service", "notification-service"]

        region = random.choice(regions)
        az_suffix = random.choice(["a", "b", "c"])
        environment = random.choices(environments, weights=[70, 20, 10])[0]  # Mostly prod
        service_name = random.choice(services)

        host = DimHost(
            host_key=str(uuid.uuid4()),
            host_id=f"i-{self.fake.hexify(text='^^^^^^^^^^^^^^^^', upper=False)}",
            host_name=f"{service_name}-{environment}-{self.fake.lexify(text='????').lower()}",
            environment=environment,
            region=region,
            availability_zone=f"{region}{az_suffix}",
            datacenter=f"dc-{region}-{random.randint(1, 5)}",
            instance_type=random.choice(instance_types),
            operating_system=random.choice(os_options),
            service_name=service_name,
            service_version=f"{random.randint(1, 3)}.{random.randint(0, 20)}.{random.randint(0, 10)}",
            cluster_name=f"{service_name}-{environment}-cluster",
            effective_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            expiration_date=None,
            is_current=True,
        )

        self.hosts.append(host)
        return host

    def create_endpoint(self) -> DimEndpoint:
        """Create a new endpoint dimension record"""
        methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
        resources = ["users", "orders", "products", "payments", "sessions", "notifications", "metrics"]
        api_versions = ["v1", "v2"]
        tiers = ["free", "basic", "premium", "enterprise"]

        method = random.choices(methods, weights=[50, 25, 10, 10, 5])[0]
        resource = random.choice(resources)
        api_version = random.choices(api_versions, weights=[30, 70])[0]

        # Generate realistic endpoint patterns
        patterns = [
            f"/api/{api_version}/{resource}",
            f"/api/{api_version}/{resource}/{{id}}",
            f"/api/{api_version}/{resource}/{{id}}/details",
            f"/api/{api_version}/{resource}/search",
            f"/api/{api_version}/{resource}/bulk",
        ]
        pattern = random.choice(patterns)

        endpoint = DimEndpoint(
            endpoint_key=str(uuid.uuid4()),
            http_method=method,
            endpoint_path=pattern,
            endpoint_pattern=pattern,
            api_version=api_version,
            resource_type=resource,
            is_authenticated=random.random() > 0.2,  # 80% authenticated
            rate_limit_tier=random.choice(tiers),
        )

        self.endpoints.append(endpoint)
        return endpoint

    def create_client(self) -> DimClient:
        """Create a new client dimension record"""
        # Weighted country distribution (US-heavy)
        countries = ["United States", "United Kingdom", "Germany", "France", "Japan", "Brazil", "Canada", "Australia"]
        country_weights = [40, 15, 10, 8, 10, 5, 7, 5]

        browsers = ["Chrome", "Firefox", "Safari", "Edge", "curl", "Python-requests"]
        devices = ["Desktop", "Mobile", "Tablet", "Server"]
        os_families = ["Windows", "macOS", "Linux", "iOS", "Android"]

        is_bot = random.random() < 0.15  # 15% bots
        device_type = "Server" if is_bot else random.choice(devices)
        user_agent = "Bot" if is_bot else random.choice(browsers)

        country = random.choices(countries, weights=country_weights)[0]

        client = DimClient(
            client_key=str(uuid.uuid4()),
            client_ip_hash=self.fake.sha256(),
            client_country=country,
            client_region=self.fake.state(),
            client_city=self.fake.city(),
            client_isp=self.fake.company(),
            user_agent_family=user_agent,
            user_agent_version=f"{random.randint(90, 120)}.0.{random.randint(1000, 9999)}",
            device_type=device_type,
            os_family=random.choice(os_families),
            is_bot=is_bot,
            api_client_id=f"client_{self.fake.uuid4()}" if random.random() > 0.5 else None,
        )

        self.clients.append(client)
        return client

    def get_random_host(self) -> DimHost:
        """Get a random existing host (or create if needed)"""
        if not self.hosts or (self.grow and random.random() < 0.05):  # 5% chance of new host
            return self.create_host()
        return random.choice(self.hosts)

    def get_random_endpoint(self) -> DimEndpoint:
        """Get a random existing endpoint (or create if needed)"""
        if not self.endpoints or (self.grow and random.random() < 0.1):  # 10% chance of new endpoint
            return self.create_endpoint()
        return random.choice(self.endpoints)

    def get_random_http_status(
        self,
        service_name: str = None,
        endpoint: "DimEndpoint" = None,
        is_business_hour: bool = True,
        is_bot: bool = False,
    ) -> DimHttpStatus:
        """Get a weighted random HTTP status with context-aware patterns"""

        # Base weights (mostly success)
        base_success_rate = 85

        # Service-specific error patterns
        service_error_multiplier = 1.0
        if service_name:
            if service_name == "payment-service":
                # Payment service has more server errors (downstream dependencies)
                service_error_multiplier = 3.5
            elif service_name == "inventory-service":
                # Inventory has occasional 503s (high load)
                service_error_multiplier = 2.5
            elif service_name == "notification-service":
                # Notifications timeout more often
                service_error_multiplier = 2.0
            elif service_name == "order-service":
                # Orders have moderate error rate
                service_error_multiplier = 1.5

        # Endpoint-specific patterns
        endpoint_error_multiplier = 1.0
        if endpoint:
            if endpoint.http_method in ["POST", "PUT", "PATCH"]:
                # Write operations fail more often
                endpoint_error_multiplier = 1.8
            if endpoint.resource_type == "payments":
                # Payment endpoints are sensitive
                endpoint_error_multiplier *= 2.0
            if endpoint.rate_limit_tier == "free":
                # Free tier hits rate limits more
                endpoint_error_multiplier *= 1.5

        # Time-based patterns
        time_multiplier = 1.0
        if not is_business_hour:
            # Off-hours have fewer errors (less load)
            time_multiplier = 0.6

        # Bot patterns
        bot_multiplier = 1.0
        if is_bot:
            # Bots get more 4xx errors (bad requests, rate limits)
            bot_multiplier = 2.5

        # Calculate effective success rate
        total_error_multiplier = service_error_multiplier * endpoint_error_multiplier * time_multiplier * bot_multiplier
        effective_success_rate = max(20, base_success_rate - (total_error_multiplier - 1) * 15)

        weights = []
        for status in self.http_statuses:
            if status.status_code == 200:
                weights.append(effective_success_rate)
            elif status.status_code == 404:
                # Bots trigger more 404s
                weights.append(3 * bot_multiplier)
            elif status.status_code == 400:
                # Bots trigger more 400s
                weights.append(2 * bot_multiplier)
            elif status.status_code == 429:
                # Rate limiting affects free tier and bots
                if endpoint and endpoint.rate_limit_tier == "free":
                    weights.append(4)
                elif is_bot:
                    weights.append(3)
                else:
                    weights.append(0.5)
            elif status.status_code == 500:
                # Payment and inventory services have more 500s
                weights.append(2 * service_error_multiplier)
            elif status.status_code == 503:
                # Inventory service has more 503s
                if service_name == "inventory-service":
                    weights.append(3 * service_error_multiplier)
                else:
                    weights.append(1.5 * service_error_multiplier)
            elif status.status_code == 504:
                # Notification service has more timeouts
                if service_name == "notification-service":
                    weights.append(2.5)
                else:
                    weights.append(1)
            else:
                weights.append(1)

        return random.choices(self.http_statuses, weights=weights)[0]

    def get_random_client(self) -> DimClient:
        """Get a random existing client (or create if needed)"""
        if not self.clients or (self.grow and random.random() < 0.2):  # 20% chance of new client
            return self.create_client()
        return random.choice(self.clients)

    def initialize_pool(self, hosts: int = 20, endpoints: int = 30, clients: int = 100):
        """Pre-populate dimension pools for realistic reuse"""
        print(f"Initializing dimension pools...")
        print(f"  Creating {hosts} hosts...")
        for i in range(hosts):
            self.create_host()

        print(f"  Creating {endpoints} endpoints...")
        for i in range(endpoints):
            self.create_endpoint()

        print(f"  Creating {clients} clients...")
        for i in range(clients):
            self.create_client()

        print(f"Dimension pools initialized!")

    def export_dimensions_to_dict(self) -> Dict[str, List[Dict[str, Any]]]:
        """Export all dimensions as dictionaries"""
        return {
            "dim_host": [asdict(h) for h in self.hosts],
            "dim_endpoint": [asdict(e) for e in self.endpoints],
            "dim_http_status": [asdict(s) for s in self.http_statuses],
            "dim_client": [asdict(c) for c in self.clients],
            "dim_date": [asdict(d) for d in self.dates.values()],
            "dim_time_of_day": [asdict(t) for t in self.times.values()],
        }
