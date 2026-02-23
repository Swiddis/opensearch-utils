"""CSV export utilities for dimension tables."""

import csv
import os
from typing import Dict, List, Any
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk


def export_dimensions_to_csv(dimensions: Dict[str, List[Dict[str, Any]]], output_dir: str = "."):
    """Export all dimension tables to CSV files."""
    if output_dir != "." and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for table_name, records in dimensions.items():
        if not records:
            continue

        filename = f"{output_dir}/{table_name}.csv"
        fieldnames = list(records[0].keys())

        with open(filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

        print(f"  Exported {len(records)} records to {filename}")


def export_dimensions_to_opensearch(
    client: OpenSearch,
    dimensions: Dict[str, List[Dict[str, Any]]],
    index_prefix: str = ""
):
    """Export all dimensions to separate OpenSearch indices."""
    table_to_index_map = {
        "dim_host": "hosts",
        "dim_endpoint": "endpoints",
        "dim_http_status": "http_status",
        "dim_client": "clients",
        "dim_date": "dates",
        "dim_time_of_day": "time_of_day",
    }

    table_to_key_field = {
        "dim_host": "host_key",
        "dim_endpoint": "endpoint_key",
        "dim_http_status": "status_key",
        "dim_client": "client_key",
        "dim_date": "date_key",
        "dim_time_of_day": "time_key",
    }

    total_count = 0
    results = {}

    for table_name, records in dimensions.items():
        if not records:
            continue

        base_index_name = table_to_index_map.get(table_name, table_name)
        index_name = f"{index_prefix}{base_index_name}" if index_prefix else base_index_name
        key_field = table_to_key_field.get(table_name, f"{table_name}_key")

        docs = []
        for record in records:
            docs.append({
                "_index": index_name,
                "_id": record.get(key_field),
                "_source": record
            })

        if docs:
            print(f"  Indexing {len(docs)} records to '{index_name}'...")
            success, failed = bulk(client, docs, raise_on_error=False)
            print(f"    Successfully indexed {success} records")
            if failed:
                print(f"    Failed to index {failed} records")
            results[table_name] = {"success": success, "failed": failed}
            total_count += success

    return total_count, results
