# Create OS Release Notes

1. Find the start and end commit hashes for the repo you want to make release notes for
2. Generate the notes

The requirements specify Python 3.10+ since we depend on `dict` being ordered for consistent
results, but it should still run without errors for lower versions.

## Usage

Install the CLI locally with `pip`. It's good practice to do this in a [virtual environment](https://docs.python.org/3/library/venv.html),
but isn't typically strictly necessary.

```bash
$ pip install .
```

Then you can run it via `make_release`.

```
$ make_release --help
Usage: make_release [OPTIONS]

Options:
  -r, --repo TEXT     The repository URL to make a release for  [required]
  -b, --base TEXT     The base commit. This is the starting point for the
                      release's changes, and *is not* included in the
                      changelog  [required]
  -h, --head TEXT     The head commit. This is the most recent commit included
                      in the release, and *is* included in the changelog
                      [required]
  -v, --version TEXT  The version to make the release notes for
  --help              Show this message and exit.
```

The `base` commit being exclusive may be counterintuitive; it comes from the script's commit search
being a thin wrapper around [Github's `compare` API](https://docs.github.com/en/pull-requests/committing-changes-to-your-project/viewing-and-comparing-commits/comparing-commits#comparing-commits),
which in turn hails from `diff` in the `git` CLI.

The script relies on the PRs in the commit range having release labels, fully defined in the
`LABEL_CATEGORIES` variable at the top of the file. It's currently configured for the labels we use
in the dashboards-observability repository. For the best results it's a good idea to introduce a
workflow that [ensures labels are set](https://github.com/opensearch-project/dashboards-observability/blob/main/.github/workflows/enforce-labels.yml).

### Example

```sh
$ make_release \
    --repo https://github.com/opensearch-project/dashboards-observability \
    --base 8b7966b09777980a6f7901eb6641e33785c93ae8 \
    --head cb78382d5f47de5d72c8fa4b001ad5d49a8bdad2 \
    --version 2.13.0 > notes.md
Generating release notes for commits 8b7966b..cb78382 on opensearch-project/dashboards-observability
Found 43 commits, searching for associated PRs
Successfully found 43 associated PRs
Generating notes
```

The notes are sent to STDOUT, while progress and supplementary info is sent to STDERR. For that
reason it's usually convenient to pipe the output into a specific markdown file. You can also pass
the `--quiet` flag to avoid the progress output.

### Rate Limiting

GitHub's API has a low per-IP rate limit for unauthenticated requests, you might regularly hit this
when working on a shared network. To get a higher rate limit, the script automatically checks for a
token in a file named `TOKEN`. You can use the [GitHub CLI](https://cli.github.com/) to quickly
generate a token:

```sh
$ gh auth login
$ gh auth token > TOKEN
```

Alternatively, you can manually create a [personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).
