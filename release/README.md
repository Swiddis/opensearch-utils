# Create OS Release Notes

1. Find the start and end commit hashes for the repo you want to make release notes for
2. Generate the notes

Requires Python 3.10+ for consistent results since it depends on `dict` being ordered, but should still run without errors for lower versions.

## Usage

```bash
$ pip install -r requirements.txt
$ python3 make-release.py --help
Usage: make-release.py [OPTIONS]

Options:
  --repo TEXT     The repository URL to make a release for  [required]
  --start TEXT    The first commit hash in the release (exclusive)  [required]
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

Alternatively, you can manually create a [personal access
token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).

### Example

```sh
$ python3 make-release.py \
    --repo https://github.com/opensearch-project/dashboards-observability \
    --start 8b7966b09777980a6f7901eb6641e33785c93ae8 \
    --end cb78382d5f47de5d72c8fa4b001ad5d49a8bdad2 \
    --version 2.13.0 > notes.md
```
