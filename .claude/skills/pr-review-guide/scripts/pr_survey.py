#!/usr/bin/env python3
"""Survey a PR before reading any of it: how big is it *really*, and what moved?

Answers the two questions that shape the whole review:
  1. How much of this diff is hand-written? (Big PRs are usually mostly generated.)
  2. If I have read it before, what changed since?

The headline number on GitHub is almost always misleading. This buckets additions
into lockfiles / generated / real, and flags "identical line count" clusters --
N files with byte-identical line counts are nearly always machine-emitted.

Usage:
  pr_survey.py 27188
  pr_survey.py https://github.com/mistralai/mistral/pull/27188
  pr_survey.py 27188 --since 6202f3a941c --repo-dir ~/workspace/mistral
"""

import argparse
import collections
import json
import re
import subprocess
import sys

DEFAULT_REPO = "mistralai/mistral"

LOCK = re.compile(r"(^|/)(uv|poetry|Cargo|package-lock|yarn|pnpm-lock|composer)\.lock$|\.lock$")
GENERATED = re.compile(
    r"(^|/)(sweeps|fixtures|snapshots|__snapshots__|testdata|vendor|generated|__generated__)/"
    r"|\.min\.(js|css)$|_pb2?\.(py|go)$|\.pb\.go$|\.generated\.\w+$"
)


def sh(*args: str) -> str:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"command failed: {' '.join(args)}\n{r.stderr}", file=sys.stderr)
        sys.exit(1)
    return r.stdout


def parse_ref(ref: str) -> tuple[str, str]:
    m = re.match(r"https?://github\.com/([^/]+/[^/]+)/pull/(\d+)", ref)
    if m:
        return m.group(1), m.group(2)
    if ref.isdigit():
        return DEFAULT_REPO, ref
    sys.exit(f"cannot parse PR ref {ref!r} -- give a number or a full PR URL")


def bucket(path: str) -> str:
    if LOCK.search(path):
        return "lock"
    if GENERATED.search(path):
        return "generated"
    return "real"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ref", help="PR number or full URL")
    ap.add_argument("--since", default=None, help="prior sha you already reviewed")
    ap.add_argument("--repo-dir", default=None, help="local clone (needed for --since)")
    a = ap.parse_args()

    repo, num = parse_ref(a.ref)

    meta = json.loads(
        sh(
            "gh", "pr", "view", num, "--repo", repo, "--json",
            "title,author,state,isDraft,createdAt,updatedAt,baseRefName,headRefName,"
            "headRefOid,additions,deletions,changedFiles,labels,commits,body",
        )
    )
    head = meta["headRefOid"]

    print(f"{'=' * 62}")
    print(f"{repo}#{num}  {meta['title']}")
    print(f"{'=' * 62}")
    print(f"author   : {meta['author']['login']} ({meta['author'].get('name') or '-'})")
    print(f"state    : {meta['state']}{'  DRAFT' if meta['isDraft'] else ''}")
    print(f"branch   : {meta['headRefName']} -> {meta['baseRefName']}")
    print(f"head     : {head}")
    print(f"updated  : {meta['updatedAt']}")
    print(f"labels   : {', '.join(l['name'] for l in meta['labels']) or '-'}")
    print(f"size     : +{meta['additions']:,} / -{meta['deletions']:,} "
          f"across {meta['changedFiles']} files")
    print(f"\ncommits ({len(meta['commits'])}):")
    for c in meta["commits"]:
        print(f"  {c['oid'][:11]}  {c['messageHeadline']}")

    # ---- per-file additions, bucketed -------------------------------------
    rows = [
        (f["additions"], f["deletions"], f["filename"])
        for f in json.loads(
            sh("gh", "api", f"repos/{repo}/pulls/{num}/files", "--paginate")
        )
    ]
    tot = sum(r[0] for r in rows) or 1
    buckets: dict[str, int] = collections.defaultdict(int)
    counts: dict[str, int] = collections.defaultdict(int)
    for add, _, fn in rows:
        b = bucket(fn)
        buckets[b] += add
        counts[b] += 1

    print(f"\n--- additions by bucket ---")
    for b in ("generated", "lock", "real"):
        if counts[b]:
            print(f"  {b:10} {buckets[b]:>8,} lines  {100*buckets[b]/tot:>3.0f}%  "
                  f"({counts[b]} files)")
    print(f"  {'TOTAL':10} {tot:>8,} lines")
    print(f"\n  >>> hand-written surface is ~{buckets['real']:,} lines "
          f"({100*buckets['real']/tot:.0f}% of the headline)")

    # ---- identical-line-count clusters (generated-file smell) --------------
    clusters = collections.defaultdict(list)
    for add, _, fn in rows:
        if add > 50:
            clusters[add].append(fn)
    big = {k: v for k, v in clusters.items() if len(v) >= 3}
    if big:
        print(f"\n--- identical line-count clusters (machine-emitted?) ---")
        for size, files in sorted(big.items(), key=lambda kv: -kv[0] * len(kv[1])):
            print(f"  {len(files)} files x {size:,} lines = {len(files)*size:,}")
            print(f"    e.g. {files[0]}")

    print(f"\n--- 15 largest by additions ---")
    for add, dele, fn in sorted(rows, reverse=True)[:15]:
        print(f"  {add:>7,}  {fn}")

    # ---- churn since a previously reviewed sha ----------------------------
    if a.since:
        if not a.repo_dir:
            print("\n--since needs --repo-dir", file=sys.stderr)
            return 2
        g = ["git", "-C", a.repo_dir]
        sh(*g, "fetch", "origin", meta["headRefName"])
        old = sh(*g, "rev-parse", a.since).strip()
        print(f"\n{'=' * 62}\nCHURN  {old[:11]} -> {head[:11]}\n{'=' * 62}")
        log = sh(*g, "log", "--oneline", f"{old}..{head}").strip()
        print(f"new commits:\n{log or '  (none)'}\n")
        stat = sh(*g, "diff", "--stat", old, head).strip().split("\n")
        print(stat[-1] if stat else "(no diff)")
        for flag, label in (("A", "ADDED"), ("D", "DELETED"), ("M", "MODIFIED")):
            names = sh(*g, "diff", "--diff-filter=" + flag, "--name-only", old, head).strip()
            if names:
                print(f"\n{label}:")
                for n in names.split("\n"):
                    print(f"  {n}")
        ren = sh(*g, "diff", "--diff-filter=R", "--name-status", "-M", old, head).strip()
        if ren:
            print(f"\nRENAMED:\n{ren}")
        print(
            "\n>>> Re-read every section of the guide that touches a DELETED, RENAMED\n"
            "    or MODIFIED path, and re-pin the whole page to the new head."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
