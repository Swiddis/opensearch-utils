"""OpenSearch connection and index management utilities."""

from typing import Dict, Any
from opensearchpy import OpenSearch

overwrite_all = False


def create_client(host: str = "localhost", port: int = 9200) -> OpenSearch:
    """Create OpenSearch client with standard configuration."""
    return OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_compress=False,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
    )


def create_fact_index(client: OpenSearch, index_name: str):
    """Create index for fact table with proper mapping."""
    mapping = {
        "settings": {
            "number_of_shards": 2,
            "number_of_replicas": 1,
            "refresh_interval": "5s",
        },
        "mappings": {
            "properties": {
                "request_id": {"type": "keyword"},
                "trace_id": {"type": "keyword"},
                "date_key": {"type": "keyword"},
                "time_key": {"type": "keyword"},
                "host_key": {"type": "keyword"},
                "endpoint_key": {"type": "keyword"},
                "status_key": {"type": "keyword"},
                "client_key": {"type": "keyword"},
                "request_timestamp": {"type": "date"},
                "latency_ms": {"type": "integer"},
                "time_to_first_byte_ms": {"type": "integer"},
                "upstream_latency_ms": {"type": "integer"},
                "bytes_sent": {"type": "long"},
                "bytes_received": {"type": "long"},
                "request_body_size": {"type": "long"},
                "response_body_size": {"type": "long"},
                "request_count": {"type": "integer"},
                "is_error": {"type": "byte"},
                "is_timeout": {"type": "byte"},
                "retry_count": {"type": "byte"},
            }
        }
    }

    if client.indices.exists(index=index_name):
        print(f"Index '{index_name}' already exists")
        response = input("Delete and recreate? (y/n/a): ")
        if response.lower() in ('y', 'a'):
            if response.lower() == 'a':
                global apply_to_all
                apply_to_all = True
            client.indices.delete(index=index_name)
            client.indices.create(index=index_name, body=mapping)
            print(f"Index '{index_name}' recreated")
    else:
        client.indices.create(index=index_name, body=mapping)
        print(f"Index '{index_name}' created")


def create_dimension_indices(client: OpenSearch, index_prefix: str = ""):
    """Create separate indices for each dimension table."""
    dimension_mappings = {
        "hosts": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
                "refresh_interval": "5s",
            },
            "mappings": {
                "properties": {
                    "host_key": {"type": "keyword"},
                    "host_id": {"type": "keyword"},
                    "host_name": {"type": "keyword"},
                    "environment": {"type": "keyword"},
                    "region": {"type": "keyword"},
                    "availability_zone": {"type": "keyword"},
                    "datacenter": {"type": "keyword"},
                    "instance_type": {"type": "keyword"},
                    "operating_system": {"type": "keyword"},
                    "service_name": {"type": "keyword"},
                    "service_version": {"type": "keyword"},
                    "cluster_name": {"type": "keyword"},
                    "effective_date": {"type": "date"},
                    "expiration_date": {"type": "date"},
                    "is_current": {"type": "boolean"},
                }
            }
        },
        "endpoints": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
                "refresh_interval": "5s",
            },
            "mappings": {
                "properties": {
                    "endpoint_key": {"type": "keyword"},
                    "http_method": {"type": "keyword"},
                    "endpoint_path": {"type": "keyword"},
                    "endpoint_pattern": {"type": "keyword"},
                    "api_version": {"type": "keyword"},
                    "resource_type": {"type": "keyword"},
                    "is_authenticated": {"type": "boolean"},
                    "rate_limit_tier": {"type": "keyword"},
                }
            }
        },
        "http_status": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
                "refresh_interval": "5s",
            },
            "mappings": {
                "properties": {
                    "status_key": {"type": "keyword"},
                    "status_code": {"type": "short"},
                    "status_text": {"type": "keyword"},
                    "status_category": {"type": "keyword"},
                    "is_success": {"type": "boolean"},
                    "is_client_error": {"type": "boolean"},
                    "is_server_error": {"type": "boolean"},
                }
            }
        },
        "clients": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
                "refresh_interval": "5s",
            },
            "mappings": {
                "properties": {
                    "client_key": {"type": "keyword"},
                    "client_ip_hash": {"type": "keyword"},
                    "client_country": {"type": "keyword"},
                    "client_region": {"type": "keyword"},
                    "client_city": {"type": "keyword"},
                    "client_isp": {"type": "keyword"},
                    "user_agent_family": {"type": "keyword"},
                    "user_agent_version": {"type": "keyword"},
                    "device_type": {"type": "keyword"},
                    "os_family": {"type": "keyword"},
                    "is_bot": {"type": "boolean"},
                    "api_client_id": {"type": "keyword"},
                }
            }
        },
        "dates": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
                "refresh_interval": "5s",
            },
            "mappings": {
                "properties": {
                    "date_key": {"type": "keyword"},
                    "full_date": {"type": "date"},
                    "day_of_week": {"type": "byte"},
                    "day_name": {"type": "keyword"},
                    "day_of_month": {"type": "byte"},
                    "day_of_year": {"type": "short"},
                    "week_of_year": {"type": "byte"},
                    "month_number": {"type": "byte"},
                    "month_name": {"type": "keyword"},
                    "quarter": {"type": "byte"},
                    "year": {"type": "short"},
                    "is_weekend": {"type": "boolean"},
                    "is_holiday": {"type": "boolean"},
                    "fiscal_quarter": {"type": "byte"},
                    "fiscal_year": {"type": "short"},
                }
            }
        },
        "time_of_day": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
                "refresh_interval": "5s",
            },
            "mappings": {
                "properties": {
                    "time_key": {"type": "keyword"},
                    "full_time": {"type": "keyword"},
                    "hour_24": {"type": "byte"},
                    "hour_12": {"type": "byte"},
                    "minute": {"type": "byte"},
                    "second": {"type": "byte"},
                    "am_pm": {"type": "keyword"},
                    "time_period": {"type": "keyword"},
                    "is_business_hour": {"type": "boolean"},
                    "hour_bucket": {"type": "keyword"},
                }
            }
        }
    }
    global apply_to_all

    created_indices = []

    for dim_name, mapping in dimension_mappings.items():
        index_name = f"{index_prefix}{dim_name}" if index_prefix else dim_name

        if client.indices.exists(index=index_name):
            print(f"Index '{index_name}' already exists")

            if not apply_to_all:
                response = input("Delete and recreate? (y/n/a): ")
                if response.lower() == 'a':
                    apply_to_all = True
                    should_recreate = True
                else:
                    should_recreate = response.lower() == 'y'
            else:
                should_recreate = apply_to_all

            if should_recreate:
                client.indices.delete(index=index_name)
                client.indices.create(index=index_name, body=mapping)
                print(f"Index '{index_name}' recreated")
                created_indices.append(index_name)
        else:
            client.indices.create(index=index_name, body=mapping)
            print(f"Index '{index_name}' created")
            created_indices.append(index_name)

    return created_indices
