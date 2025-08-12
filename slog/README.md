# Slog: sorted log diving

When working with logs from many-node clusters,
you often want to sort those logs chronologically given the inputs of per-node logs.
But just doing `cat * | sort` isn't always ideal because the logs can get very large (leading to `sort` bottlenecks),
and also some logs contain multi-line entries that get mangled by sorting.

This CLI takes log file globs, prettifies them, and merges them, streaming the entries to stdout.
It's highly parallelized, causing it to go faster than `wc` on my machine (albeit with more user CPU time).

Since I needed this for a specific log format, the `colorize` logic parses those logs.
For other formats you may want to tweak this logic.
For timestamp sorting, it assumes the log timestamp is the leftmost field.
For identifying log entries, there's also the `is_log_line_start` method that probably needs to be tweaked.
I was working with OpenSearch logs that look like this:

```
[2025-06-20T09:00:03,079][INFO ][o.o.n.c.logger           ] [node1] GET /_cluster/state local=true&filter_path=metadata.cluster_coordination%2Cversion 200 OK 195 3
[2025-06-20T09:00:03,523][INFO ][o.o.n.c.logger           ] [node1] GET /_nodes/_local/stats/shard_indexing_pressure top= 200 OK 3274 0
[2025-06-20T09:00:04,004][INFO ][o.o.n.c.logger           ] [node2] GET /_cat/master - 200 OK 119 0
```

## Installing

With [Rust's Cargo installed](https://www.rust-lang.org/tools/install), just install:

```sh
$ cargo install --path .
```

## Usage

```
slog <pattern> [pattern2 ...] [--no-color]
```
