import re
import string
import sys

import click
import requests


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


class GitHubClient:
    _token: str | None = None

    def __init__(self, owner, repo):
        self.owner = owner
        self.repo = repo
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"
        self._init_token()

    def _init_token(self):
        try:
            with open("TOKEN", "r") as token_file:
                self._token = token_file.read().strip()
        except FileNotFoundError:
            self._token = None

    def fetch(self, path):
        url, headers = f"{self.base_url}/{path}", {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers = {"Authorization": f"Bearer {self._token}"}

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(
                f"Error {response.status_code}: {response.json()['message']}",
                file=sys.stderr,
            )
            sys.exit(1)

    def fetch_commits(self, base_commit, head_commit):
        data = self.fetch(f"compare/{base_commit}...{head_commit}")
        commits = data.get("commits", [])
        return commits

    def fetch_merged_prs(self, targets: set[str]):
        targets = targets.copy()
        page_size = 50
        # Assume that if the PR is not in the first 5 pages, it doesn't exist
        for page in range(1, 6):
            if not len(targets):
                return
            result = self.fetch(
                f"pulls?state=closed&sort=updated&direction=desc&page={page}&per_page={page_size}"
            )
            for pr in result:
                if str(pr["number"]) in targets:
                    yield pr
                    targets.remove(str(pr["number"]))
            if len(result) < page_size:
                return # Out of pages


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


def get_commit_pr(commit) -> str | None:
    headline = commit["commit"]["message"].split("\n")[0]
    linked_prs = re.findall(r"\(\#(\d+)\)", headline)
    oldest_pr = min(linked_prs, key=int, default=None)
    return oldest_pr


def extract_category(labels):
    labels = [label["name"] for label in labels]
    for category in LABEL_CATEGORIES:
        if category in labels:
            return category
    return "unknown"


def assemble_contrib_data(pull_req):
    return {
        "pull_req": str(pull_req["number"]),
        "author": pull_req["user"]["login"],
        "title": pull_req["title"],
        "category": extract_category(pull_req["labels"]),
        "link": pull_req["html_url"]
    }


def split_categories(contrib_data: dict):
    categories = {key: [] for key in LABEL_CATEGORIES}
    for data in contrib_data:
        categories[data["category"]].append(data)
    return categories


def make_notes(contrib_data: dict, version: str):
    categories = split_categories(contrib_data)

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
            result += f"* {title.strip()} ([#{pull_req['pull_req']}]({pull_req['link']}))\n"
        result += "\n"
    return result[:-2]  # Remove extra trailing newlines


@click.command(name='make_release')
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
    help="The first commit hash in the release (inclusive)",
    callback=validate_commit_hash,
)
@click.option(
    "--end",
    required=True,
    help="The last commit hash in the release (inclusive)",
    callback=validate_commit_hash,
)
@click.option(
    "--version", help="The version to make the release notes for", default="[VERSION]"
)
def make_release(repo_parts: tuple[str, str], start: str, end: str, version: str):
    owner, repo = repo_parts
    client = GitHubClient(owner, repo)

    print(
        f"Generating release notes for commits {start[:7]}..{end[:7]} on {owner}/{repo}",
        file=sys.stderr,
    )

    commits = client.fetch_commits(start, end)

    print(f"Found {len(commits)} commits, searching for associated PRs", file=sys.stderr)

    pr_nums = {get_commit_pr(commit) for commit in commits}
    pr_nums = {pc for pc in pr_nums if pc}
    results = [
        assemble_contrib_data(pr)
        for pr in client.fetch_merged_prs(pr_nums)
    ]

    print(f"Successfully found {len(results)} associated PRs", file=sys.stderr)
    if len(results) < len(pr_nums):
        print(f"Unable to find PRs: {pr_nums - set(r['pull_req'] for r in results)}", file=sys.stderr)

    print("Generating notes", file=sys.stderr)

    notes = make_notes(results, version)
    print(notes)


if __name__ == "__main__":
    make_release()
