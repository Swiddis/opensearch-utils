# OpenSearch Bulk Indexer

![Photo of it in action](media/image.png)

Utility CLI for indexing files in OpenSearch as fast as possible.

## Installation

Clone & cd to this directory, then just install with Cargo:

```
% cargo install --path .
```

## Usage

This indexes the specified newline-delimited json file into an index, respecting the compression specified in the extension.
Alternative endpoints and auth details are optional.

```
$ bulk-index --help
Bulk index documents into OpenSearch/Elasticsearch

Usage: bulk-index [OPTIONS] --file <FILE> --index <INDEX>

Options:
  -f, --file <FILE>
          Path to the dataset file (supports .json, .json.gz, .json.zst)
  -i, --index <INDEX>
          Target index name
  -e, --endpoint <ENDPOINT>
          OpenSearch/Elasticsearch endpoint URL [default: http://localhost:9200]
  -u, --username <USERNAME>
          Username for HTTP basic authentication
  -p, --password <PASSWORD>
          Password for HTTP basic authentication
  -l, --limit <LIMIT>
          Maximum number of lines to read (optional, reads all if not specified)
  -b, --batch-size <BATCH_SIZE>
          Number of documents per batch [default: 8192]
  -c, --concurrent-requests <CONCURRENT_REQUESTS>
          Maximum number of concurrent requests [default: 32]
      --max-pending-batches <MAX_PENDING_BATCHES>
          Maximum number of in-progress batches to concurrently keep in memory [default: 64]
  -h, --help
          Print help
```
