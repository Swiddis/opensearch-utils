#!/usr/bin/env python3
"""
Generate example enrichment data for testing dimension-style joins.
Extracts unique keys from OpenSearch index and generates fake enrichment data.
"""

import csv
import sys

from src.opensearch_utils import create_client
from src.enrichment import (
    get_unique_values,
    get_unique_values_via_scan,
    generate_enrichment_data,
)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate enrichment CSV data from OpenSearch index keys"
    )
    parser.add_argument(
        "--host", default="localhost", help="OpenSearch host (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=9200, help="OpenSearch port (default: 9200)"
    )
    parser.add_argument(
        "--index", default="big5", help="Index name to extract keys from (default: big5)"
    )
    parser.add_argument(
        "--key-field",
        default="agent_id",
        help="Field to use as primary key (default: agent_id)",
    )
    parser.add_argument(
        "--output",
        default="enrichment.csv",
        help="Output CSV file (default: enrichment.csv)",
    )
    parser.add_argument(
        "--max-keys",
        type=int,
        default=None,
        help="Maximum number of unique keys to generate enrichment for (default: all)",
    )
    parser.add_argument(
        "--use-scan",
        action="store_true",
        help="Use document scanning instead of aggregations (slower but works on all field types)",
    )

    args = parser.parse_args()

    try:
        client = create_client(args.host, args.port)

        print(f"Extracting unique {args.key_field} values from '{args.index}' index...")

        if args.use_scan:
            unique_keys = get_unique_values_via_scan(
                client, args.index, args.key_field, args.max_keys
            )
        else:
            try:
                unique_keys = get_unique_values(
                    client, args.index, args.key_field, args.max_keys
                )
            except Exception as e:
                print(f"Aggregation failed, falling back to scan method: {e}", file=sys.stderr)
                unique_keys = get_unique_values_via_scan(
                    client, args.index, args.key_field, args.max_keys
                )

        if not unique_keys:
            print(f"No values found for field '{args.key_field}' in index '{args.index}'")
            sys.exit(1)

        print(f"Found {len(unique_keys)} unique {args.key_field} values")

        print("Generating enrichment data...")
        enrichment_data = generate_enrichment_data(unique_keys, args.key_field)

        if enrichment_data:
            fieldnames = list(enrichment_data[0].keys())
            with open(args.output, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(enrichment_data)

            print(f"Enrichment data written to {args.output}")
            print(f"Total records: {len(enrichment_data)}")
            print(f"Fields: {', '.join(fieldnames)}")
        else:
            print("No enrichment data generated!")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
