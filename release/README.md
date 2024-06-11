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
$ make_release --help
Usage: make_release [OPTIONS]

Options:
  --repo TEXT     The repository URL to make a release for  [required]
  --start TEXT    The first commit hash in the release (inclusive)  [required]
  --end TEXT      The last commit hash in the release (inclusive)  [required]
  --version TEXT  The version to make the release notes for
  --help          Show this message and exit.
```

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

### Example

```sh
$ make_release \
    --repo https://github.com/opensearch-project/dashboards-observability \
    --start 8b7966b09777980a6f7901eb6641e33785c93ae8 \
    --end cb78382d5f47de5d72c8fa4b001ad5d49a8bdad2 \
    --version 2.13.0 > notes.md
```
