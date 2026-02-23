"""Enrichment data generation utilities."""

import sys
from typing import Any, Dict, List, Optional
from opensearchpy import OpenSearch
from faker import Faker


def get_unique_values(
    client: OpenSearch,
    index_name: str,
    field_name: str,
    max_values: Optional[int] = None,
) -> List[str]:
    """Get unique values for a field using aggregations."""
    size = max_values if max_values else 10000

    agg_body = {
        "size": 0,
        "aggs": {
            "unique_values": {
                "terms": {
                    "field": f"{field_name}.keyword" if not field_name.endswith(".keyword") else field_name,
                    "size": size,
                }
            }
        },
    }

    try:
        response = client.search(index=index_name, body=agg_body)
        buckets = response["aggregations"]["unique_values"]["buckets"]
        return [bucket["key"] for bucket in buckets]
    except Exception as e:
        print(f"Warning: Could not use aggregation on {field_name}, trying keyword version", file=sys.stderr)
        if not field_name.endswith(".keyword"):
            agg_body["aggs"]["unique_values"]["terms"]["field"] = f"{field_name}.keyword"
            response = client.search(index=index_name, body=agg_body)
            buckets = response["aggregations"]["unique_values"]["buckets"]
            return [bucket["key"] for bucket in buckets]
        else:
            raise e


def get_unique_values_via_scan(
    client: OpenSearch,
    index_name: str,
    field_name: str,
    max_values: Optional[int] = None,
) -> List[str]:
    """Fallback method: Get unique values by scanning documents."""
    unique_values = set()
    batch_size = 1000

    search_body = {
        "size": batch_size,
        "sort": [{"_id": "asc"}],
        "_source": [field_name],
        "query": {
            "exists": {
                "field": field_name
            }
        },
    }

    print(f"Scanning index for unique {field_name} values...", file=sys.stderr)
    response = client.search(index=index_name, body=search_body)

    while True:
        hits = response["hits"]["hits"]
        if not hits:
            break

        for hit in hits:
            value = hit["_source"]
            for part in field_name.split("."):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    value = None
                    break

            if value is not None:
                unique_values.add(str(value))

            if max_values and len(unique_values) >= max_values:
                return list(unique_values)[:max_values]

        last_sort = hits[-1]["sort"]
        search_body["search_after"] = last_sort
        response = client.search(index=index_name, body=search_body)

    return list(unique_values)


def generate_enrichment_data(
    primary_keys: List[str],
    key_field_name: str = "agent_id",
) -> List[Dict[str, Any]]:
    """Generate fake enrichment data for given primary keys."""
    fake = Faker()
    Faker.seed(42)

    enrichment_data = []

    business_units = ["Engineering", "Sales", "Marketing", "Operations", "Finance", "HR"]
    priority_levels = ["Critical", "High", "Medium", "Low"]
    regions = ["US-East", "US-West", "EU-Central", "EU-West", "APAC", "LATAM"]
    departments = ["Infrastructure", "Security", "Development", "Analytics", "Support", "DevOps"]

    for key in primary_keys:
        record = {
            key_field_name: key,
            "team_name": fake.company(),
            "cost_center": fake.numerify(text="CC-####"),
            "business_unit": fake.random_element(business_units),
            "department": fake.random_element(departments),
            "manager_name": fake.name(),
            "manager_email": fake.email(),
            "region": fake.random_element(regions),
            "location": fake.city(),
            "priority_level": fake.random_element(priority_levels),
            "budget_allocated": fake.random_int(min=10000, max=1000000),
            "employee_count": fake.random_int(min=1, max=500),
            "project_code": fake.bothify(text="PRJ-????-####"),
            "status": fake.random_element(["Active", "Inactive", "Pending", "Archived"]),
            "created_date": fake.date_between(start_date="-2y", end_date="today").isoformat(),
            "last_updated": fake.date_between(start_date="-6m", end_date="today").isoformat(),
        }
        enrichment_data.append(record)

    return enrichment_data
