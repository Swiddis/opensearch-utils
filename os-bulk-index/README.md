# OpenSearch Bulk Indexer

![Photo of it in action](media/image.png)

Utility CLI for indexing files in OpenSearch as fast as possible.

Currently configured to load the big5 dataset from OpenSearch Benchmark.
Requires a newline-delimited JSON file with ZST compression.

If there's demand, I'm happy to make this easier to tweak (e.g. CLI arguments), and make it support multiple file formats.

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
  -f, --file <FILE>          Path to the dataset file (supports .json, .json.gz, .json.zst)
  -i, --index <INDEX>        Target index name
  -e, --endpoint <ENDPOINT>  OpenSearch/Elasticsearch endpoint URL [default: http://localhost:9200]
  -u, --username <USERNAME>  Username for HTTP basic authentication
  -p, --password <PASSWORD>  Password for HTTP basic authentication
  -l, --limit <LIMIT>        Maximum number of lines to read (optional, reads all if not specified)
  -h, --help                 Print help
```
