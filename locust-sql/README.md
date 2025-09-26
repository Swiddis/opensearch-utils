# OpenSearch PPL in Locust

Quick set of files for load-testing OpenSearch PPL. For best results, make sure to resource-constrain OpenSearch to a handful of CPUs.

## Usage

Set up the `uv` environment, then run `locust` against your cluster:

```sh
$ uv sync
$ .venv/bin/locust --host=http://localhost:9200/
```
