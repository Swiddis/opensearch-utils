# OpenSearch Dimensional Data Tools

Tools for working with dimensional data in OpenSearch - generating Kimball-style dimensional logs and creating enrichment tables for testing analytics queries.

## Features

- **Dimensional Log Generation**: Creates realistic request logs following Kimball star schema methodology
- **Dimension Management**: Manages host, endpoint, client, status, date, and time dimensions with realistic reuse patterns
- **Enrichment Data**: Generates fake enrichment tables from OpenSearch index keys
- **Flexible Export**: Exports dimensions to CSV files or OpenSearch indices
- **Dynamic Rate Control**: Supports variable ingestion rates using Perlin noise
- **Historical Backfill**: Can generate historical data with realistic timestamps

## Installation

```bash
uv sync
```

## Project Structure

The project follows a modular architecture with a `src/` directory pattern:

```
/
├── generate_dimensional_logs.py    # Entry point for log generation
├── generate_enrichment.py          # Entry point for enrichment generation
├── src/
│   ├── dimensions.py               # Dimension table management
│   ├── fact_generator.py           # Fact record generation with business logic
│   ├── opensearch_utils.py         # OpenSearch connection and index management
│   ├── csv_export.py               # CSV and OpenSearch export utilities
│   ├── rate_limiter.py             # Dynamic rate calculation using Perlin noise
│   └── enrichment.py               # Enrichment data generation utilities
```

Each module has a single responsibility:
- **dimensions.py**: Manages dimension tables following Kimball methodology
- **fact_generator.py**: Generates realistic fact records with correlated measures
- **opensearch_utils.py**: Handles OpenSearch connections and index creation
- **csv_export.py**: Exports dimensions to CSV files or OpenSearch indices
- **rate_limiter.py**: Calculates dynamic ingestion rates
- **enrichment.py**: Extracts keys and generates fake enrichment data

---

## Dimensional Log Generator

The `generate_dimensional_logs.py` script creates realistic dimensional server request logs following Kimball star schema methodology. Perfect for testing analytics features and dimension enrichment.

### Features

- **Kimball Star Schema**: Implements proper dimensional modeling with fact and dimension tables
- **Realistic Dimension Reuse**: Simulates real-world patterns where dimensions are reused (95% reuse for hosts, 90% for endpoints, 80% for clients)
- **Rate-Limited Generation**: Generates logs at configurable rate (default 100 logs/second)
- **Batch Indexing**: Efficient bulk indexing to OpenSearch
- **CSV Export**: Exports all dimension tables to CSV for enrichment testing

### Dimensional Model

The schema includes:
- **Fact Table**: `fact_request_log` - One row per HTTP request with measures (latency, bytes, errors)
- **Dimensions**:
  - `dim_host` - Server/host information (Type 2 SCD)
  - `dim_endpoint` - API endpoint details
  - `dim_http_status` - HTTP status codes
  - `dim_client` - Client/user-agent information
  - `dim_date` - Date dimension
  - `dim_time_of_day` - Time of day dimension (15-min buckets)

### Usage

Basic usage (generates logs infinitely at 100/sec, press Ctrl+C to stop):
```bash
python generate_dimensional_logs.py
```

With options:
```bash
# Generate for a specific duration
python generate_dimensional_logs.py --duration 300  # Run for 5 minutes

# Generate at higher rate
python generate_dimensional_logs.py --rate 500

# Custom index name
python generate_dimensional_logs.py --index prod_requests

# Larger batches for better performance
python generate_dimensional_logs.py --batch-size 500

# Skip dimension export
python generate_dimensional_logs.py --no-export-dimensions

# Custom dimension output directory
python generate_dimensional_logs.py --dimension-dir ./my_dimensions
```

### Options

- `--host`: OpenSearch host (default: localhost)
- `--port`: OpenSearch port (default: 9200)
- `--index`: Index name (default: request_logs)
- `--rate`: Target logs per second (default: 100)
- `--duration`: Duration in seconds (default: infinite, run until Ctrl+C)
- `--batch-size`: Batch size for indexing (default: 100)
- `--no-export-dimensions`: Skip exporting dimension CSVs
- `--dimension-dir`: Output directory for dimension CSVs (default: ./dimensions)

### Example

```bash
# Generate logs continuously, export dimensions
python generate_dimensional_logs.py --dimension-dir ./dimensions
# Press Ctrl+C when you have enough data

# Generate exactly 30,000 logs over 5 minutes
python generate_dimensional_logs.py --rate 100 --duration 300 --dimension-dir ./dimensions

# Then use the dimension CSVs for enrichment testing
ls dimensions/
# dim_host.csv  dim_endpoint.csv  dim_client.csv  dim_http_status.csv  dim_date.csv  dim_time_of_day.csv
```

### What Gets Generated

**Fact Records** include:
- Foreign keys to all dimensions
- Measures: latency_ms, bytes_sent/received, error flags
- Denormalized fields for easy querying (host_name, service_name, status_code, etc.)

**Dimension Records** include realistic:
- Hosts: 20 initial hosts across prod/staging/dev environments
- Endpoints: 30 API endpoints with different methods and patterns
- Clients: 100 unique clients from various countries and device types
- HTTP Statuses: All common status codes (200, 404, 500, etc.)
- Dates/Times: Automatically generated based on log timestamps

### Analytics Queries

See [docs/example_queries.md](docs/example_queries.md) for 14 realistic analytics queries demonstrating:
- Service health monitoring and error rate analysis
- API usage patterns and rate limiting
- Geographic traffic distribution and CDN optimization
- Cost analysis and bandwidth optimization
- Performance analysis by time of day and day of week
- Multi-dimensional dashboards combining all dimensions

Each query shows the business value and demonstrates proper use of the `lookup` command for dimensional enrichment.

---

## Enrichment Data Generator

The `generate_enrichment.py` script creates example dimension-style enrichment tables for testing joins with query results.

### Features

- Extracts unique primary keys from an OpenSearch index (e.g., `agent_id`)
- Generates fake enrichment data using Faker library
- Creates analyst-style dimension tables for local development
- Supports custom fields and configurable output

### Usage

Basic usage (extracts agent_ids from big5):
```bash
python generate_enrichment.py
```

With options:
```bash
# Use different primary key field
python generate_enrichment.py --key-field host.name

# Custom output file
python generate_enrichment.py --output agent_enrichment.csv

# Limit number of keys
python generate_enrichment.py --max-keys 1000

# Use document scanning (slower, but works on all field types)
python generate_enrichment.py --use-scan
```

### Options

- `--host`: OpenSearch host (default: localhost)
- `--port`: OpenSearch port (default: 9200)
- `--index`: Index to extract keys from (default: big5)
- `--key-field`: Field to use as primary key (default: agent_id)
- `--output`: Output CSV file (default: enrichment.csv)
- `--max-keys`: Maximum unique keys to process (default: all)
- `--use-scan`: Use document scanning instead of aggregations

### Generated Fields

The enrichment data includes:
- Primary key field (e.g., `agent_id`)
- `team_name`: Company/team name
- `cost_center`: Cost center code
- `business_unit`: Business unit category
- `department`: Department name
- `manager_name`: Manager full name
- `manager_email`: Manager email address
- `region`: Geographic region
- `location`: City location
- `priority_level`: Priority classification
- `budget_allocated`: Budget amount
- `employee_count`: Team size
- `project_code`: Project identifier
- `status`: Current status
- `created_date`: Creation date
- `last_updated`: Last update date

### Example

```bash
# Generate enrichment data for agent_id dimension
python generate_enrichment.py --key-field agent_id --output agent_dimension.csv

# Generate enrichment data for host.name dimension
python generate_enrichment.py --key-field host.name --output host_dimension.csv --use-scan
```
