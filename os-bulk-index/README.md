# OpenSearch Bulk Indexer

![Photo of it in action](media/image.png)

Utility CLI for indexing files in OpenSearch as fast as possible.
It also supports scanning indices via `--scan`, which is useful for saving test datasets, or cross-cluster reindexing without hassle.

## Installation

Clone & cd to this directory, then just install with Cargo:

```
% cargo install --path .
```

## Usage

This indexes the specified newline-delimited json file (or SQLite table) into an index, respecting the compression specified in the extension.
Alternative endpoints and auth details are optional.

### Indexing from a file

```bash
$ bulk-index --help
Bulk index documents into OpenSearch/Elasticsearch, or scan/export them

Usage: bulk-index [OPTIONS] --index <INDEX>

Options:
  -i, --index <INDEX>
          Target index name
  -e, --endpoint <ENDPOINT>
          OpenSearch/Elasticsearch endpoint URL [default: http://localhost:9200]
  -u, --username <USERNAME>
          Username for HTTP basic authentication
  -p, --password <PASSWORD>
          Password for HTTP basic authentication
      --scan
          Scan mode: export documents from the index to stdout as NDJSON
  -f, --file <FILE>
          Path to the dataset file (supports .json, .json.gz, .json.bz2, .json.zst). Defaults to stdin if not provided
  -l, --limit <LIMIT>
          Maximum number of lines to read (optional, reads all if not specified)
  -b, --batch-size <BATCH_SIZE>
          Number of documents per batch [default: 4096]
  -c, --concurrent-requests <CONCURRENT_REQUESTS>
          Maximum number of concurrent requests [default: 32]
      --max-pending-batches <MAX_PENDING_BATCHES>
          Maximum number of in-progress batches to concurrently keep in memory [default: 64]
      --live
          Live mode: skip _id field and replace timestamps with current time
  -r, --rate <RATE>
          Rate limit in documents per second (optional, no limit if not specified)
      --scroll-timeout <SCROLL_TIMEOUT>
          Scroll timeout for scan operations (e.g., "1m", "30s") [default: 1m]
      --query <QUERY>
          Query to filter documents during scan (JSON query DSL)
      --scroll-size <SCROLL_SIZE>
          Size of each scroll batch [default: 1000]
      --sqlite-db <SQLITE_DB>
          SQLite database path (alternative to --file)
      --sqlite-table <SQLITE_TABLE>
          Table name to read from SQLite database
  -h, --help
          Print help
```

### Indexing from SQLite

You can index directly from a SQLite database table:

```bash
bulk-index -i my-index --sqlite-db /path/to/database.db --sqlite-table my_table
```

This converts each row to a JSON document with column names as fields. SQLite types map naturally:
- INTEGER/REAL → JSON numbers
- TEXT → JSON strings (including timestamps, which are passed as-is)
- BLOB → base64-encoded strings
- NULL → JSON null

The tool relies on OpenSearch's dynamic mapping to interpret field types. For timestamp fields, ensure your index has appropriate date format patterns configured.
