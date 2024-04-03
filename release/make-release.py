import collections
import json
import re
import string
import sys

import click
import requests
from tqdm import tqdm


MIN_HASH_LENGTH = 7
LABEL_CATEGORIES = {
    "breaking": "Breaking",
    "enhancement": "Features",
    "bug": "Bug Fixes",
    "infrastructure": "Infrastructure",
    "documentation": "Documentation",
    "maintenance": "Maintenance",
    "unknown": "UNKNOWN (Needs Manual Categorization)",
}


def validate_commit_hash(_ctx, _param, commit_hash: str):
    if not all(c in string.hexdigits for c in commit_hash):
        raise click.BadParameter(f"Commit hash '{commit_hash}' is not hexadecimal")
    if len(commit_hash) < MIN_HASH_LENGTH:
        raise click.BadParameter(
            f"Commit hash '{commit_hash}' too short: min length is {MIN_HASH_LENGTH}"
        )
    return commit_hash


def parse_repo_url(_ctx, _param, repo_url: str):
    if not (
        repo_url.startswith("http://github.com")
        or repo_url.startswith("https://github.com")
    ):
        raise click.BadParameter(f"Repo '{repo_url}' not a GitHub URL")
    if repo_url.startswith("http://"):
        repo_url = "https://" + repo_url.removeprefix("http://")
    owner, repo = repo_url.removeprefix("https://github.com/").split("/")[:2]
    return (owner, repo)


def fetch_github(path):
    # If repeatedly running this for lots of commits, the rate limit is severe. Try to cache:
    try:
        with open("cache.json", "r") as cachefile:
            cache = json.load(cachefile)
    except:
        cache = {}
    if path in cache:
        return cache[path]

    url = f"https://api.github.com/{path}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()

        cache[path] = data
        with open("cache.json", "w") as cachefile:
            json.dump(cache, cachefile)

        return data
    else:
        print(
            f"Error {response.status_code}: {response.json()['message']}",
            file=sys.stderr,
        )
        sys.exit(1)


def fetch_commits(owner, repo, base_commit, head_commit):
    data = fetch_github(f"repos/{owner}/{repo}/compare/{base_commit}...{head_commit}")
    commits = data.get("commits", [])
    return commits


def fetch_pull_req(owner, repo, pull_number):
    data = fetch_github(f"repos/{owner}/{repo}/pulls/{pull_number}")
    return data


def parse_commit(owner, repo, commit):
    message = commit["commit"]["message"].split("\n")[0]
    message_parts = re.match(r".+?\(\#(\d+)\).*", message)
    if not message_parts:
        print(
            f"WARN: Unable to parse commit {commit['sha']}: {message}; ignoring",
            file=sys.stderr,
        )
        return None

    parse = {
        "pull_req": message_parts.group(1),
    }
    pull_req = fetch_pull_req(owner, repo, parse["pull_req"])
    parse["author"] = pull_req["user"]["login"]
    parse["title"] = pull_req["title"]
    parse["labels"] = [label["name"] for label in pull_req["labels"]]

    return parse


def extract_category(labels):
    for category in LABEL_CATEGORIES:
        if category in labels:
            return category
    return "unknown"


def make_notes(categories: dict[str, list], owner, repo, version):
    result = f"## Version {version} Release Notes\n\n"
    result += (
        f"Compatible with OpenSearch and OpenSearch Dashboards version {version}\n\n"
    )
    for lcat, title in LABEL_CATEGORIES.items():
        if len(categories[lcat]) == 0:
            continue
        result += f"### {title}\n"
        for pull_req in sorted(
            categories[lcat], key=lambda p: int(p["pull_req"]), reverse=True
        ):
            title = (
                pull_req["title"]
                if not pull_req["title"].startswith("[")
                else pull_req["title"].split("]", maxsplit=1)[1]
            )
            result += f"* {title.strip()} ([#{pull_req['pull_req']}](https://github.com/{owner}/{repo}/pull/{pull_req['pull_req']}))\n"
        result += "\n"
    return result[:-2] # Remove extra trailing newlines


@click.command()
@click.option(
    "--repo",
    "repo_parts",
    required=True,
    help="The repository URL to make a release for",
    callback=parse_repo_url,
)
@click.option(
    "--start",
    required=True,
    help="The first commit hash in the release (exclusive)",
    callback=validate_commit_hash,
)
@click.option(
    "--end",
    required=True,
    help="The last commit hash in the release (inclusive)",
    callback=validate_commit_hash,
)
@click.option(
    "--version", help="The version to make the release notes for", default="[TODO]"
)
def make_release(repo_parts: tuple[str, str], start: str, end: str, version: str):
    owner, repo = repo_parts

    print(
        f"Generating release notes for commits {start[:7]}..{end[:7]} on {owner}/{repo}",
        file=sys.stderr,
    )

    commits = fetch_commits(owner, repo, start, end)

    print(f"Found {len(commits)} commits", file=sys.stderr)

    categories = collections.defaultdict(lambda: [])
    for commit in tqdm(commits, desc="Processing commits", file=sys.stderr):
        parsed = parse_commit(owner, repo, commit)
        if not parsed:
            continue
        categories[extract_category(parsed["labels"])].append(parsed)

    print("Generating notes", file=sys.stderr)

    notes = make_notes(categories, owner, repo, version)
    print(notes)


if __name__ == "__main__":
    make_release()
