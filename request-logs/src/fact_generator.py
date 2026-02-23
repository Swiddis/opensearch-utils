"""Generates fact records with dimensional references."""

import uuid
from datetime import datetime
from typing import Dict, Any

from src.dimensions import DimensionManager


class FactRequestLogGenerator:
    """Generates fact records with dimensional references."""

    def __init__(self, dimension_manager: DimensionManager):
        self.dim_mgr = dimension_manager

    def generate_fact(self, timestamp: datetime = None, denormalized: bool = False) -> Dict[str, Any]:
        """Generate a single fact record."""
        if timestamp is None:
            timestamp = datetime.now()

        host = self.dim_mgr.get_random_host()
        endpoint = self.dim_mgr.get_random_endpoint()
        client = self.dim_mgr.get_random_client()
        date_dim = self.dim_mgr.get_or_create_date(timestamp)
        time_dim = self.dim_mgr.get_time(timestamp)

        status = self.dim_mgr.get_random_http_status(
            service_name=host.service_name,
            endpoint=endpoint,
            is_business_hour=time_dim.is_business_hour,
            is_bot=client.is_bot,
        )

        is_error = not status.is_success
        is_timeout = status.status_code in [504, 408] if is_error else False

        base_latency = self._calculate_base_latency(host, client, time_dim, date_dim)
        latency_ms = self._calculate_final_latency(base_latency, status)
        time_to_first_byte = int(latency_ms * self.dim_mgr.fake.random.uniform(0.3, 0.6))
        upstream_latency = int(latency_ms * self.dim_mgr.fake.random.uniform(0.5, 0.8))

        request_body_size = self._calculate_request_body_size(endpoint)
        response_body_size = self._calculate_response_body_size(status)
        bytes_sent = response_body_size + self.dim_mgr.fake.random.randint(100, 500)
        bytes_received = request_body_size + self.dim_mgr.fake.random.randint(100, 300)

        retry_count = self.dim_mgr.fake.random.randint(1, 3) if is_error and self.dim_mgr.fake.random.random() < 0.3 else 0

        fact = {
            "request_id": str(uuid.uuid4()),
            "trace_id": str(uuid.uuid4()),
            "request_timestamp": timestamp.isoformat(),
            "latency_ms": latency_ms,
            "time_to_first_byte_ms": time_to_first_byte,
            "upstream_latency_ms": upstream_latency,
            "bytes_sent": bytes_sent,
            "bytes_received": bytes_received,
            "request_body_size": request_body_size,
            "response_body_size": response_body_size,
            "request_count": 1,
            "is_error": 1 if is_error else 0,
            "is_timeout": 1 if is_timeout else 0,
            "retry_count": retry_count,
        }

        if denormalized:
            fact.update({
                "host_id": host.host_id,
                "host_name": host.host_name,
                "environment": host.environment,
                "region": host.region,
                "availability_zone": host.availability_zone,
                "datacenter": host.datacenter,
                "instance_type": host.instance_type,
                "operating_system": host.operating_system,
                "service_name": host.service_name,
                "service_version": host.service_version,
                "cluster_name": host.cluster_name,
                "http_method": endpoint.http_method,
                "endpoint_path": endpoint.endpoint_path,
                "endpoint_pattern": endpoint.endpoint_pattern,
                "api_version": endpoint.api_version,
                "resource_type": endpoint.resource_type,
                "is_authenticated": endpoint.is_authenticated,
                "rate_limit_tier": endpoint.rate_limit_tier,
                "status_code": status.status_code,
                "status_text": status.status_text,
                "status_category": status.status_category,
                "client_ip_hash": client.client_ip_hash,
                "client_country": client.client_country,
                "client_region": client.client_region,
                "client_city": client.client_city,
                "client_isp": client.client_isp,
                "user_agent_family": client.user_agent_family,
                "user_agent_version": client.user_agent_version,
                "device_type": client.device_type,
                "os_family": client.os_family,
                "is_bot": client.is_bot,
                "api_client_id": client.api_client_id,
                "full_date": date_dim.full_date,
                "day_of_week": date_dim.day_of_week,
                "day_name": date_dim.day_name,
                "month_name": date_dim.month_name,
                "quarter": date_dim.quarter,
                "year": date_dim.year,
                "is_weekend": date_dim.is_weekend,
                "is_holiday": date_dim.is_holiday,
                "hour_24": time_dim.hour_24,
                "time_period": time_dim.time_period,
                "is_business_hour": time_dim.is_business_hour,
            })
        else:
            fact.update({
                "date_key": date_dim.date_key,
                "time_key": time_dim.time_key,
                "host_key": host.host_key,
                "endpoint_key": endpoint.endpoint_key,
                "status_key": status.status_key,
                "client_key": client.client_key,
            })

        return fact

    def _calculate_base_latency(self, host, client, time_dim, date_dim) -> float:
        """Calculate base latency considering multiple factors."""
        base_latency = 50.0

        if host.instance_type.startswith("t3."):
            base_latency *= 1.4
        elif host.instance_type.startswith("c5."):
            base_latency *= 0.7
        elif host.instance_type.startswith("m5."):
            base_latency *= 1.0

        if host.region in ["ap-southeast-1", "eu-central-1"]:
            base_latency *= 1.3
        elif host.region == "us-east-1":
            base_latency *= 0.9

        major_version = int(host.service_version.split(".")[0])
        if major_version == 1:
            base_latency *= 1.5
        elif major_version == 3:
            base_latency *= 0.85

        if host.service_name == "payment-service":
            base_latency *= 1.6
        elif host.service_name == "notification-service":
            base_latency *= 1.4
        elif host.service_name == "inventory-service":
            base_latency *= 1.2

        if client.client_country in ["Japan", "Brazil", "Australia"]:
            base_latency *= 1.4
        elif client.client_country in ["Germany", "France", "United Kingdom"]:
            base_latency *= 1.2

        if time_dim.is_business_hour:
            base_latency *= 1.15

        if date_dim.is_weekend:
            base_latency *= 0.85

        return base_latency

    def _calculate_final_latency(self, base_latency: float, status) -> int:
        """Calculate final latency based on status."""
        if status.is_success:
            return int(max(5, self.dim_mgr.fake.random.gauss(base_latency, base_latency * 0.4)))
        elif status.is_server_error:
            return int(max(50, self.dim_mgr.fake.random.gauss(base_latency * 4, base_latency * 2)))
        else:
            return int(max(5, self.dim_mgr.fake.random.gauss(base_latency * 0.6, base_latency * 0.3)))

    def _calculate_request_body_size(self, endpoint) -> int:
        """Calculate request body size based on HTTP method."""
        if endpoint.http_method in ["POST", "PUT", "PATCH"]:
            return self.dim_mgr.fake.random.randint(100, 50000)
        return 0

    def _calculate_response_body_size(self, status) -> int:
        """Calculate response body size based on status."""
        if status.is_success:
            return self.dim_mgr.fake.random.randint(200, 100000)
        return self.dim_mgr.fake.random.randint(50, 500)
