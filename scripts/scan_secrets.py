"""Fail CI when credential material appears anywhere in Git history.

Scanning only the working tree misses a secret that was committed and later deleted. This
command therefore refuses shallow clones and examines every added line in every reachable patch.
"""
from __future__ import annotations

import re
import subprocess
import sys


PATTERNS = {
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    "Slack webhook": re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]{20,}"),
    "GCP private key": re.compile(r'"private_key"\s*:\s*"-----BEGIN'),
}


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], text=True, encoding="utf-8", errors="replace"
    )


def main() -> int:
    try:
        shallow = git("rev-parse", "--is-shallow-repository").strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"SECRET SCAN ERROR: not a readable Git repository: {exc}", file=sys.stderr)
        return 2
    if shallow == "true":
        print(
            "SECRET SCAN ERROR: shallow history is unsafe; checkout with fetch-depth: 0",
            file=sys.stderr,
        )
        return 2

    committed_names = set(
        git("log", "--all", "--name-only", "--pretty=format:").splitlines()
    )
    forbidden_names = sorted(
        name for name in committed_names
        if name == "cloud.env" or name.endswith((".pem", ".p12", ".pfx"))
    )

    patch = git(
        "log", "-p", "--all", "--no-ext-diff", "--unified=0", "--pretty=format:commit %H"
    )
    findings: list[tuple[str, str]] = []
    commit = "unknown"
    for line in patch.splitlines():
        if line.startswith("commit "):
            commit = line.removeprefix("commit ").strip()
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added = line[1:]
        for label, pattern in PATTERNS.items():
            if pattern.search(added):
                findings.append((commit[:12], label))

    if forbidden_names or findings:
        print("SECRET SCAN FAILED", file=sys.stderr)
        for name in forbidden_names:
            print(f"  forbidden credential filename in history: {name}", file=sys.stderr)
        for commit_id, label in findings:
            print(f"  {commit_id}: possible {label}", file=sys.stderr)
        print("Rotate exposed credentials before rewriting history.", file=sys.stderr)
        return 1

    print("SECRET SCAN PASSED — complete Git history checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
