#!/usr/bin/env python3
"""
Updates the PROJECTS table in README.md using GitHub's GraphQL API.
Shows pinned repos first; fills remaining slots with recently-pushed public repos.
"""

import json
import os
import re
import sys
import urllib.request

USERNAME = "AndreaPallotta"
TARGET = 6
START_MARKER = "<!-- PROJECTS:START -->"
END_MARKER = "<!-- PROJECTS:END -->"

GRAPHQL_QUERY = """
query($username: String!) {
  user(login: $username) {
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes {
        ... on Repository {
          name
          description
          url
          languages(first: 4, orderBy: {field: SIZE, direction: DESC}) {
            nodes { name }
          }
        }
      }
    }
    repositories(
      first: 20
      orderBy: {field: PUSHED_AT, direction: DESC}
      privacy: PUBLIC
      isFork: false
    ) {
      nodes {
        name
        description
        url
        isArchived
        languages(first: 4, orderBy: {field: SIZE, direction: DESC}) {
          nodes { name }
        }
      }
    }
  }
}
"""


def graphql_request(query: str, variables: dict) -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("Error: GITHUB_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "readme-updater",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def build_row(repo: dict) -> str:
    name = repo["name"]
    url = repo["url"]
    desc = (repo.get("description") or "").strip() or "-"
    langs = [n["name"] for n in (repo.get("languages") or {}).get("nodes", [])]
    stack = " · ".join(langs[:4]) if langs else "—"
    # Escape underscores in name for markdown tables
    md_name = name.replace("_", "\\_")
    return f"| [**{md_name}**]({url}) | {desc} | {stack} |"


def build_table(repos: list) -> str:
    header = "| Project | Description | Stack |\n|---------|-------------|-------|"
    rows = "\n".join(build_row(r) for r in repos)
    return f"{header}\n{rows}"


def main():
    result = graphql_request(GRAPHQL_QUERY, {"username": USERNAME})

    if "errors" in result:
        print("GraphQL errors:", result["errors"], file=sys.stderr)
        sys.exit(1)

    user = result["data"]["user"]
    pinned = [n for n in user["pinnedItems"]["nodes"] if n]
    recent = [
        n for n in user["repositories"]["nodes"]
        if n
        and not n.get("isArchived")
        and n["name"] != USERNAME  # skip the profile repo itself
    ]

    # Pinned first, then fill up to TARGET with recent (deduped by name)
    pinned_names = {r["name"] for r in pinned}
    fill = [r for r in recent if r["name"] not in pinned_names]
    combined = (pinned + fill)[:TARGET]

    if not combined:
        print("No repos found — aborting to avoid wiping the table.", file=sys.stderr)
        sys.exit(1)

    table = build_table(combined)

    readme_path = os.path.join(os.path.dirname(__file__), "..", "README.md")
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        re.DOTALL,
    )
    if not pattern.search(content):
        print("Markers not found in README.md — aborting.", file=sys.stderr)
        sys.exit(1)

    replacement = f"{START_MARKER}\n{table}\n{END_MARKER}"
    new_content = re.sub(pattern, replacement, content)

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(
        f"✅ Updated README with {len(combined)} projects "
        f"({len(pinned)} pinned + {len(combined) - len(pinned)} recent)"
    )


if __name__ == "__main__":
    main()
