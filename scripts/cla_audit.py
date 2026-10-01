#!/usr/bin/env python3
"""List contributors whose code is in the tree but who have not signed the CLA.

Blames every tracked text file at HEAD, maps each commit author to a GitHub
login, and compares the result with the signature store that
.github/workflows/cla.yml commits to the `cla-signatures` branch.

    GH_TOKEN=... python scripts/cla_audit.py              # Markdown report
    GH_TOKEN=... python scripts/cla_audit.py --json out.json

An author is mapped by their GitHub no-reply address, else by the GitHub
account linked to the commit email. Commits by AI agents or unlinked emails
are credited to the author of the pull request that merged them, because that
person submitted the work. Without a token the GitHub API rate limit runs out
quickly; unresolved authors are then listed by email. Blame follows moves
within a file only, so code copied between files is credited to whoever moved
it.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SLUG = "debpalash/VoiceStudio"
SIGNATURES = "origin/cla-signatures:signatures/cla.json"
EXEMPT = re.compile(r"^(debpalash|.*\[bot\])$")
BINARY = re.compile(r"\.(lock|png|jpe?g|gif|webp|ico|icns|svg|wav|mp3|flac|ogg|woff2?|ttf|pdf|onnx|bin)$", re.I)
NOREPLY = re.compile(r"^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$", re.I)
# Identities that do not name the person who submitted the work.
AGENT = re.compile(r"^(noreply@anthropic\.com|.*@openai\.com|codex@users\.noreply\.github\.com|test@local|you@example\.com|)$")
NOTES = {
    "lookup-failed": "GitHub lookup failed; set GH_TOKEN and rerun",
    "name": "matched by display name; confirm",
    "unresolved": "no linked account or pull request; resolve by hand",
}


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, errors="replace").stdout


def github(path: str) -> object:
    request = urllib.request.Request(f"https://api.github.com/repos/{SLUG}/{path}")
    if token := os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def blame(path: str) -> collections.Counter:
    lines: collections.Counter = collections.Counter()
    commit = name = email = None
    for row in git("blame", "-w", "-M", "--line-porcelain", "HEAD", "--", path).splitlines():
        if re.match(r"^[0-9a-f]{40} ", row):
            commit = row[:40]
        elif row.startswith("author "):
            name = row[7:]
        elif row.startswith("author-mail "):
            email = row[12:].strip("<>").lower()
        elif row.startswith("\t"):
            lines[(email, name, commit, path)] += 1
    return lines


def names_to_logins() -> dict[str, str]:
    """Display names seen with a GitHub no-reply address, as author or co-author."""
    names: dict[str, str] = {}
    log = git("log", "--format=%aN <%aE>%n%(trailers:key=Co-authored-by,valueonly)")
    for match in re.finditer(r"^(.+?) <([^>]+)>$", log, re.M):
        if (login := NOREPLY.match(match.group(2))) and not AGENT.match(match.group(2).lower()):
            names.setdefault(match.group(1).strip().lower(), login.group(1))
    return names


def account_for(email: str, commit: str) -> tuple[str | None, str]:
    """GitHub account linked to an author email: (login, noreply|api|unlinked|lookup-failed)."""
    if AGENT.match(email):
        return None, "unlinked"
    if match := NOREPLY.match(email):
        return match.group(1), "noreply"
    try:
        login = (github(f"commits/{commit}").get("author") or {}).get("login")
    except (OSError, ValueError):
        return None, "lookup-failed"
    return (login, "api") if login else (None, "unlinked")


def pr_author_for(commit: str) -> tuple[str | None, str]:
    try:
        pulls = github(f"commits/{commit}/pulls")
    except (OSError, ValueError):
        return None, "lookup-failed"
    return (pulls[0]["user"]["login"], "pr-author") if pulls else (None, "unresolved")


def signed_logins() -> set[str]:
    raw = git("show", SIGNATURES)
    return {entry["name"].lower() for entry in json.loads(raw)["signedContributors"]} if raw else set()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", type=Path, help="also write the full report as JSON")
    args = parser.parse_args()

    files = [f for f in git("ls-files").splitlines() if f and not BINARY.search(f)]
    blamed: collections.Counter = collections.Counter()
    with ThreadPoolExecutor(16) as pool:
        for counts in pool.map(blame, files):
            blamed.update(counts)

    first_commit: dict[str, str] = {}
    for email, _, commit, _ in blamed:
        first_commit.setdefault(email, commit)
    with ThreadPoolExecutor(8) as pool:
        accounts = dict(zip(first_commit, pool.map(lambda e: account_for(e, first_commit[e]), first_commit)))

    # Unlinked and agent identities are resolved per commit to the PR author.
    per_commit = sorted({c for e, _, c, _ in blamed if accounts[e][1] == "unlinked"})
    with ThreadPoolExecutor(8) as pool:
        pr_authors = dict(zip(per_commit, pool.map(pr_author_for, per_commit)))

    names = names_to_logins()
    signed = signed_logins()
    people: dict[str, dict] = collections.defaultdict(
        lambda: {"lines": 0, "files": collections.Counter(), "emails": set(), "notes": set(), "login": None}
    )
    for (email, name, commit, path), n in blamed.items():
        login, source = accounts[email]
        if source == "unlinked":
            login, source = pr_authors[commit]
        if not login and (guess := names.get(name.strip().lower())):
            login, source = guess, "name"
        # A display-name guess never exempts anyone.
        if login and EXEMPT.match(login) and source != "name":
            continue
        who = login or email or name
        person = people[who]
        person["lines"] += n
        person["files"][path] += n
        person["emails"].add(email)
        person["login"] = login
        if source in NOTES:
            person["notes"].add(source)

    unsigned = sorted(
        ((who, p) for who, p in people.items() if who.lower() not in signed),
        key=lambda item: -item[1]["lines"],
    )
    print(f"# CLA audit — {len(unsigned)} unsigned of {len(people)} contributors with code at HEAD\n")
    print("| Contributor | Lines at HEAD | Largest files |\n|---|---:|---|")
    for who, p in unsigned:
        label = f"@{who}" if p["login"] else f"`{who}`"
        if p["notes"]:
            label += " (" + "; ".join(NOTES[n] for n in sorted(p["notes"])) + ")"
        top = ", ".join(f"`{f}` ({n})" for f, n in p["files"].most_common(3))
        print(f"| {label} | {p['lines']} | {top} |")

    if args.json:
        args.json.write_text(json.dumps(
            {who: {"lines": p["lines"], "emails": sorted(p["emails"]), "signed": who.lower() in signed,
                   "notes": sorted(p["notes"]), "files": p["files"].most_common()} for who, p in people.items()},
            indent=1,
        ))


if __name__ == "__main__":
    main()
