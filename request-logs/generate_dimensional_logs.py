#!/usr/bin/env python3
"""
Generate dimensional server request logs and index to OpenSearch.
Follows Kimball dimensional modeling with realistic dimension reuse.
"""

import time
import sys
import random
from datetime import datetime, timedelta
from opensearchpy.helpers import bulk

from src.dimensions import DimensionManager
from src.fact_generator import FactRequestLogGenerator
from src.opensearch_utils import create_client, create_fact_index, create_dimension_indices
from src.csv_export import export_dimensions_to_csv, export_dimensions_to_opensearch
from src.rate_limiter import calculate_dynamic_rate


def generate_and_index_logs(
    host: str = "localhost",
    port: int = 9200,
    index_name: str = "request_logs",
    rate_per_second: int = 100,
    duration_seconds: int = None,
    batch_size: int = 100,
    export_dimensions: bool = True,
    dimension_output_dir: str = ".",
    dimension_export_interval: int = 30,
    dynamic_rate: bool = False,
    min_rate: int = None,
    max_rate: int = None,
    rate_time_scale: float = 0.01,
    grow: bool = False,
    export_lookup: bool = False,
    lookup_index: str = "",
    backfill_minutes: int = 0,
    single_index: bool = False,
):
    """Generate and index dimensional logs at specified rate."""
    if single_index:
        export_dimensions = False
        export_lookup = False
    
    if dynamic_rate:
        if min_rate is None:
            min_rate = int(rate_per_second * 0.5)
        if max_rate is None:
            max_rate = int(rate_per_second * 1.5)
    else:
        min_rate = rate_per_second
        max_rate = rate_per_second

    client = create_client(host, port)

    print("Initializing dimensions...")
    dim_mgr = DimensionManager(grow=grow)
    dim_mgr.initialize_pool(hosts=300, endpoints=3000, clients=30000)

    print(f"\nCreating index '{index_name}'...")
    create_fact_index(client, index_name)

    if export_lookup:
        print(f"\nCreating dimension indices...")
        create_dimension_indices(client, index_prefix=lookup_index)
        print(f"\nExporting dimensions to indices...")
        dimensions = dim_mgr.export_dimensions_to_dict()
        export_dimensions_to_opensearch(client, dimensions, index_prefix=lookup_index)

    fact_generator = FactRequestLogGenerator(dim_mgr)

    backfill_indexed = 0
    if backfill_minutes > 0:
        backfill_indexed = _backfill_historical_data(
            client, index_name, fact_generator, backfill_minutes,
            rate_per_second, min_rate, max_rate, rate_time_scale,
            batch_size, dynamic_rate, single_index
        )

    _print_generation_header(rate_per_second, min_rate, max_rate, duration_seconds,
                             batch_size, export_dimensions, dimension_output_dir,
                             dimension_export_interval, dynamic_rate)

    total_generated, total_indexed = _generate_realtime_logs(
        client, index_name, fact_generator, dim_mgr, rate_per_second,
        duration_seconds, batch_size, min_rate, max_rate, rate_time_scale,
        export_dimensions, dimension_output_dir, dimension_export_interval,
        export_lookup, lookup_index, grow, dynamic_rate, single_index
    )

    _print_summary(total_generated, total_indexed, backfill_indexed, time.time())

    if export_dimensions:
        print(f"\nExporting dimension tables to {dimension_output_dir}...")
        dimensions = dim_mgr.export_dimensions_to_dict()
        export_dimensions_to_csv(dimensions, dimension_output_dir)
        print("Dimensions exported!")

    print(f"\nDimension Statistics:")
    print(f"  Hosts: {len(dim_mgr.hosts)}")
    print(f"  Endpoints: {len(dim_mgr.endpoints)}")
    print(f"  Clients: {len(dim_mgr.clients)}")
    print(f"  Dates: {len(dim_mgr.dates)}")
    print(f"  HTTP Statuses: {len(dim_mgr.http_statuses)}")


def _backfill_historical_data(
    client, index_name, fact_generator, backfill_minutes,
    rate_per_second, min_rate, max_rate, rate_time_scale,
    batch_size, dynamic_rate, single_index
):
    """Generate and index historical data."""
    if dynamic_rate:
        print(f"\nBackfilling {backfill_minutes} minutes of historical data with dynamic rate...")
    else:
        print(f"\nBackfilling {backfill_minutes} minutes of historical data...")

    backfill_start_time = datetime.now() - timedelta(minutes=backfill_minutes)
    backfill_end_time = datetime.now()
    base_backfill_records = int(rate_per_second * backfill_minutes * 60)

    if dynamic_rate:
        print(f"  Generating ~{base_backfill_records} records (varying with dynamic rate) from {backfill_start_time.strftime('%Y-%m-%d %H:%M:%S')} to {backfill_end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print(f"  Generating {base_backfill_records} records from {backfill_start_time.strftime('%Y-%m-%d %H:%M:%S')} to {backfill_end_time.strftime('%Y-%m-%d %H:%M:%S')}")

    backfill_batch = []
    total_backfill_seconds = backfill_minutes * 60
    backfill_indexed = 0

    if dynamic_rate:
        backfill_time_offset = -1000
        total_generated_in_backfill = 0

        for second in range(total_backfill_seconds):
            elapsed_at_second = backfill_time_offset + second
            current_rate = calculate_dynamic_rate(
                elapsed_at_second, rate_per_second, min_rate, max_rate, rate_time_scale
            )

            timestamp = backfill_start_time + timedelta(seconds=second)
            for _ in range(current_rate):
                timestamp_with_variance = timestamp + timedelta(milliseconds=random.random() * 1000)
                fact = fact_generator.generate_fact(timestamp_with_variance, denormalized=single_index)
                backfill_batch.append({"_index": index_name, "_source": fact})
                total_generated_in_backfill += 1

            if len(backfill_batch) >= batch_size:
                success, failed = bulk(client, backfill_batch, raise_on_error=False)
                backfill_indexed += success
                backfill_batch = []

            if (second + 1) % max(1, total_backfill_seconds // 10) == 0:
                percent = ((second + 1) / total_backfill_seconds) * 100
                print(f"  Progress: {percent:.0f}% ({total_generated_in_backfill} records generated)")
    else:
        backfill_progress_interval = max(1, base_backfill_records // 10)

        for i in range(base_backfill_records):
            progress = i / base_backfill_records
            timestamp = backfill_start_time + timedelta(seconds=progress * backfill_minutes * 60)

            fact = fact_generator.generate_fact(timestamp, denormalized=single_index)
            backfill_batch.append({"_index": index_name, "_source": fact})

            if len(backfill_batch) >= batch_size:
                success, failed = bulk(client, backfill_batch, raise_on_error=False)
                backfill_indexed += success
                backfill_batch = []

            if (i + 1) % backfill_progress_interval == 0:
                percent = ((i + 1) / base_backfill_records) * 100
                print(f"  Progress: {percent:.0f}% ({i + 1}/{base_backfill_records} records)")

    if backfill_batch:
        success, failed = bulk(client, backfill_batch, raise_on_error=False)
        backfill_indexed += success

    print(f"  Backfill complete! Indexed {backfill_indexed} historical records")
    print()

    return backfill_indexed


def _print_generation_header(rate_per_second, min_rate, max_rate, duration_seconds,
                             batch_size, export_dimensions, dimension_output_dir,
                             dimension_export_interval, dynamic_rate):
    """Print generation configuration."""
    if duration_seconds is None:
        if dynamic_rate:
            print(f"\nGenerating logs with dynamic rate (base: {rate_per_second}, range: {min_rate}-{max_rate} logs/sec)")
            print(f"  (infinite, press Ctrl+C to stop)")
        else:
            print(f"\nGenerating logs at {rate_per_second} logs/second (infinite, press Ctrl+C to stop)...")
    else:
        if dynamic_rate:
            print(f"\nGenerating logs with dynamic rate (base: {rate_per_second}, range: {min_rate}-{max_rate} logs/sec)")
            print(f"  for {duration_seconds} seconds")
        else:
            print(f"\nGenerating logs at {rate_per_second} logs/second for {duration_seconds} seconds...")
    print(f"Batch size: {batch_size}")
    if export_dimensions:
        print(f"Dimension exports: every {dimension_export_interval}s to {dimension_output_dir}")


def _generate_realtime_logs(
    client, index_name, fact_generator, dim_mgr, rate_per_second,
    duration_seconds, batch_size, min_rate, max_rate, rate_time_scale,
    export_dimensions, dimension_output_dir, dimension_export_interval,
    export_lookup, lookup_index, grow, dynamic_rate, single_index
):
    """Generate and index real-time logs."""
    total_generated = 0
    total_indexed = 0
    batch = []

    start_time = time.time()
    next_report = start_time + 5
    next_dimension_export = start_time + dimension_export_interval if export_dimensions else None

    target_total = rate_per_second * duration_seconds if duration_seconds else None
    current_rate = rate_per_second

    try:
        while target_total is None or total_generated < target_total:
            current_time = time.time()
            elapsed = current_time - start_time

            if dynamic_rate:
                current_rate = calculate_dynamic_rate(
                    elapsed, rate_per_second, min_rate, max_rate, rate_time_scale
                )

            batches_per_second = current_rate / batch_size
            sleep_time = 1.0 / batches_per_second if batches_per_second > 0 else 0

            batch_timestamp = datetime.now()
            for _ in range(batch_size):
                if target_total is not None and total_generated >= target_total:
                    break

                timestamp_offset = timedelta(milliseconds=random.random() * 1000 / batches_per_second)
                fact = fact_generator.generate_fact(batch_timestamp + timestamp_offset, denormalized=single_index)
                batch.append({"_index": index_name, "_source": fact})
                total_generated += 1

            if batch:
                success, failed = bulk(client, batch, raise_on_error=False)
                total_indexed += success
                batch = []

            current_time = time.time()
            if current_time >= next_report:
                elapsed = current_time - start_time
                actual_rate = total_indexed / elapsed if elapsed > 0 else 0
                if dynamic_rate:
                    if target_total is None:
                        print(f"  Indexed {total_indexed} logs (target: {current_rate} logs/sec, actual: {actual_rate:.1f} logs/sec)")
                    else:
                        print(f"  Indexed {total_indexed}/{target_total} logs (target: {current_rate} logs/sec, actual: {actual_rate:.1f} logs/sec)")
                else:
                    if target_total is None:
                        print(f"  Indexed {total_indexed} logs ({actual_rate:.1f} logs/sec)")
                    else:
                        print(f"  Indexed {total_indexed}/{target_total} logs ({actual_rate:.1f} logs/sec)")
                next_report = current_time + 5

            if next_dimension_export is not None and current_time >= next_dimension_export:
                print(f"  Exporting dimensions to {dimension_output_dir}...")
                dimensions = dim_mgr.export_dimensions_to_dict()
                export_dimensions_to_csv(dimensions, dimension_output_dir)

                if export_lookup and grow:
                    print(f"  Updating dimension indices...")
                    export_dimensions_to_opensearch(client, dimensions, index_prefix=lookup_index)

                next_dimension_export = current_time + dimension_export_interval

            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")

    if batch:
        success, failed = bulk(client, batch, raise_on_error=False)
        total_indexed += success

    return total_generated, total_indexed


def _print_summary(total_generated, total_indexed, backfill_indexed, start_time):
    """Print generation summary statistics."""
    elapsed = time.time() - start_time
    actual_rate = total_indexed / elapsed if elapsed > 0 else 0

    print(f"\n{'='*60}")
    print(f"Generation complete!")
    if backfill_indexed > 0:
        print(f"  Backfill logs indexed: {backfill_indexed}")
    print(f"  Real-time logs generated: {total_generated}")
    print(f"  Real-time logs indexed: {total_indexed}")
    print(f"  Total logs indexed: {total_indexed + backfill_indexed}")
    print(f"  Time elapsed: {elapsed:.1f} seconds")
    print(f"  Actual rate: {actual_rate:.1f} logs/second")
    print(f"{'='*60}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate dimensional request logs and index to OpenSearch"
    )
    parser.add_argument(
        "--host", default="localhost", help="OpenSearch host (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=9200, help="OpenSearch port (default: 9200)"
    )
    parser.add_argument(
        "--index",
        default="request_logs",
        help="Index name (default: request_logs)",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=100,
        help="Target logs per second (default: 100)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Duration in seconds (default: infinite, press Ctrl+C to stop)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for indexing (default: 100)",
    )
    parser.add_argument(
        "--no-export-dimensions",
        action="store_true",
        help="Skip exporting dimension CSVs",
    )
    parser.add_argument(
        "--dimension-dir",
        default="./dimensions",
        help="Output directory for dimension CSVs (default: ./dimensions)",
    )
    parser.add_argument(
        "--dimension-export-interval",
        type=int,
        default=30,
        help="Seconds between dimension exports (default: 30)",
    )
    parser.add_argument(
        "--dynamic-rate",
        action="store_true",
        help="Enable dynamic rate variation using Perlin noise",
    )
    parser.add_argument(
        "--grow-dimensions",
        action="store_true",
        help="Continually generate new values in dimensions instead of using a static list"
    )
    parser.add_argument(
        "--min-rate",
        type=int,
        default=None,
        help="Minimum rate per second for dynamic rate (default: rate * 0.5)",
    )
    parser.add_argument(
        "--max-rate",
        type=int,
        default=None,
        help="Maximum rate per second for dynamic rate (default: rate * 1.5)",
    )
    parser.add_argument(
        "--rate-time-scale",
        type=float,
        default=0.01,
        help="Time scale for rate changes (lower = slower changes, default: 0.01)",
    )
    parser.add_argument(
        "--lookup",
        action="store_true",
        help="Export dimensions to OpenSearch as separate indices (one per dimension). When combined with --grow-dimensions, indices are updated periodically with new dimension records.",
    )
    parser.add_argument(
        "--lookup-index",
        default="",
        help="Index prefix for dimension indices (default: none, creates hosts, endpoints, http_status, clients, dates, time_of_day)",
    )
    parser.add_argument(
        "--backfill-minutes",
        type=int,
        default=0,
        help="Minutes of historical data to generate at startup (default: 0, e.g., 15 for 15 minutes)",
    )
    parser.add_argument(
        "--single-index",
        action="store_true",
        help="Embed all dimension data directly in fact records instead of using foreign keys (faster queries, no joins needed)",
    )

    args = parser.parse_args()

    try:
        generate_and_index_logs(
            host=args.host,
            port=args.port,
            index_name=args.index,
            rate_per_second=args.rate,
            duration_seconds=args.duration,
            batch_size=args.batch_size,
            export_dimensions=not args.no_export_dimensions,
            dimension_output_dir=args.dimension_dir,
            dimension_export_interval=args.dimension_export_interval,
            dynamic_rate=args.dynamic_rate,
            min_rate=args.min_rate,
            max_rate=args.max_rate,
            rate_time_scale=args.rate_time_scale,
            grow=args.grow_dimensions,
            export_lookup=args.lookup,
            lookup_index=args.lookup_index,
            backfill_minutes=args.backfill_minutes,
            single_index=args.single_index,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
