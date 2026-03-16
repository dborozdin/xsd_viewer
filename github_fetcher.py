"""Fetch XSD files from a GitHub repository URL.

Supports URLs like:
  https://github.com/{owner}/{repo}/tree/{branch}/{path}
"""
from __future__ import annotations

import os
import re
from typing import Optional

import requests


def parse_github_url(url: str) -> tuple[str, str, str, str]:
    """Parse a GitHub URL into (owner, repo, branch, path).

    Supports:
      https://github.com/owner/repo/tree/branch/path/to/dir
      https://github.com/owner/repo  (defaults to branch='main', path='')
    """
    url = url.strip().rstrip("/")

    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)(?:/(.*))?",
        url,
    )
    if m:
        owner, repo, branch, path = m.group(1), m.group(2), m.group(3), m.group(4) or ""
        return owner, repo, branch, path

    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/?$", url)
    if m:
        return m.group(1), m.group(2), "main", ""

    raise ValueError(
        f"Cannot parse GitHub URL: {url}\n"
        "Expected format: https://github.com/owner/repo/tree/branch/path"
    )


def fetch_xsd_files(url: str, target_dir: str) -> list[str]:
    """Fetch all .xsd files from a GitHub directory URL.

    Downloads files to target_dir via the GitHub Contents API.
    Returns a list of downloaded filenames.

    Raises requests.HTTPError on API errors (e.g. rate limiting).
    """
    owner, repo, branch, path = parse_github_url(url)

    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    params = {"ref": branch}
    headers = {"Accept": "application/vnd.github.v3+json"}

    resp = requests.get(api_url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()

    contents = resp.json()
    if not isinstance(contents, list):
        raise ValueError(f"Expected a directory listing, got: {type(contents).__name__}")

    downloaded: list[str] = []
    for item in contents:
        name = item.get("name", "")
        if not name.lower().endswith(".xsd"):
            continue
        download_url = item.get("download_url")
        if not download_url:
            continue

        file_resp = requests.get(download_url, timeout=30)
        file_resp.raise_for_status()

        file_path = os.path.join(target_dir, name)
        with open(file_path, "wb") as f:
            f.write(file_resp.content)
        downloaded.append(name)

    return downloaded
