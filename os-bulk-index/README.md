# OpenSearch Bulk Indexer

Utility for indexing files in OpenSearch as fast as possible.

Currently configured to load the big5 dataset from OpenSearch Benchmark.
Requires a newline-delimited JSON file with ZST compression.

If there's demand, I'm happy to make this easier to tweak (e.g. CLI arguments), and make it support multiple file formats.

## Usage

Tweak the constants to your liking and then run it:

```
$ cargo run --release -- [lines_to_load]
```

![Photo of it in action](image.png)
