#!/usr/bin/env python3
"""Rewrite the "Latest commits" table in README.md from the GitHub REST API.

Shows the latest commit from each of the most recently active public repositories.
Only public repositories are listed, so private work never reaches the README.
On any API failure the script exits non-zero and leaves the README untouched.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER = os.environ.get("PROFILE_USER", "gabrimoreira")
README = Path(os.environ.get("README_PATH", "README.md"))
ROWS = 5
MAX_REPOS_CHECKED = 12
MAX_MESSAGE_LENGTH = 72
LOCAL_TIME = timezone(timedelta(hours=-3))  # Fortaleza, no daylight saving
START = "<!-- recent-commits:start -->"
END = "<!-- recent-commits:end -->"


def get(path):
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "profile-readme"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def escape_message(message):
    """Make untrusted commit text inert inside a Markdown table link."""
    subject = message.splitlines()[0] if message.strip() else "(no message)"
    subject = re.sub(r"[\x00-\x1f\x7f]", "", subject).strip()
    if len(subject) > MAX_MESSAGE_LENGTH:
        subject = subject[: MAX_MESSAGE_LENGTH - 1].rstrip() + "…"
    subject = subject.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_{}\[\]()#+!|~])", r"\\\1", subject)


def latest_commit(repo):
    """Return the newest non-merge commit by USER, or None if the repo has none."""
    try:
        commits = get(f"/repos/{USER}/{repo['name']}/commits?author={USER}&per_page=10")
    except urllib.error.HTTPError as error:
        if error.code == 409:  # GitHub answers 409 for an empty repository
            return None
        raise
    for commit in commits:
        if len(commit["parents"]) <= 1:
            return commit
    return None


def collect_rows():
    repos = get(f"/users/{USER}/repos?sort=pushed&direction=desc&per_page=30")
    candidates = [
        repo
        for repo in repos
        if not repo["fork"] and not repo["archived"] and repo["name"].lower() != USER.lower()
    ]
    rows = []
    for repo in candidates[:MAX_REPOS_CHECKED]:
        commit = latest_commit(repo)
        if commit is None:
            continue
        date = datetime.fromisoformat(commit["commit"]["author"]["date"].replace("Z", "+00:00"))
        rows.append((date, repo, commit))
        if len(rows) == ROWS:
            break
    rows.sort(key=lambda row: row[0], reverse=True)
    return rows


def render(rows):
    lines = ["| Repository | Commit | Date |", "| --- | --- | --- |"]
    for date, repo, commit in rows:
        lines.append(
            f"| [`{repo['name']}`]({repo['html_url']}) "
            f"| [{escape_message(commit['commit']['message'])}]({commit['html_url']}) "
            f"| {date.astimezone(LOCAL_TIME):%b&nbsp;%d,&nbsp;%Y} |"  # stays on one line
        )
    return "\n".join(lines)


def main():
    readme = README.read_text(encoding="utf-8")
    if readme.count(START) != 1 or readme.count(END) != 1:
        print(f"::error::{README} must contain each recent-commits marker exactly once", file=sys.stderr)
        return 1
    try:
        rows = collect_rows()
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as error:
        print(f"::error::GitHub API request failed: {error}", file=sys.stderr)
        return 1
    if not rows:
        print("::error::No commits found, keeping the current table", file=sys.stderr)
        return 1
    before, _, rest = readme.partition(START)
    _, _, after = rest.partition(END)
    updated = f"{before}{START}\n{render(rows)}\n{END}{after}"
    if updated != readme:
        README.write_text(updated, encoding="utf-8")
    print(render(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
