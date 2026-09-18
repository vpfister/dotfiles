#!/usr/bin/env python3
"""Verify every link and anchor in a generated PR review guide.

Checks, in order of how badly they bite:
  1. HTML parses.
  2. Every internal #anchor resolves to a real id.
  3. Every data-gh path exists at the reviewed commit.
  4. Every data-gh line range is within the file's length.
  5. HEURISTIC: every range's FIRST line looks like a declaration, not a
     mid-construct continuation. This is the check that matters -- an in-bounds
     range that starts on a blank line or a closing bracket points the reader at
     nothing. Review these by eye; they are warnings, not errors.

Usage:
  verify_links.py --html DIR/index.html --repo-dir ~/workspace/mistral --commit <sha>
  verify_links.py ... --old-commit <sha>   # also check ⧖ before/after links

Exit 1 if any hard error (2,3,4). Warnings alone exit 0.
"""

import argparse
import html.parser
import pathlib
import re
import subprocess
import sys

GH_BLOB_RE = re.compile(
    r'https://github\.com/[^/]+/[^/]+/blob/(?P<sha>[0-9a-f]{40})/(?P<target>[^"\'#\s]+(?:#L\d+(?:-L\d+)?)?)'
)

# A range whose first line matches one of these is probably mid-construct.
SUSPICIOUS = re.compile(r"^\s*(\)|\]|\}|,|\.|\"\"\"|'''|#|$)")


class Parser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.hrefs, self.datagh = set(), [], []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if d.get("id"):
            self.ids.add(d["id"])
        if d.get("href"):
            self.hrefs.append(d["href"])
        if d.get("data-gh"):
            self.datagh.append(d["data-gh"])

    def error(self, msg):
        raise RuntimeError(msg)


def git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True
    )


def obj_type(repo: str, sha: str, path: str) -> str | None:
    r = git(repo, "cat-file", "-t", f"{sha}:{path}")
    return r.stdout.strip() if r.returncode == 0 else None


def file_lines(repo: str, sha: str, path: str) -> list[str]:
    r = git(repo, "show", f"{sha}:{path}")
    return r.stdout.split("\n") if r.returncode == 0 else []


def split_target(t: str) -> tuple[str, int | None, int | None]:
    if "#" not in t:
        return t, None, None
    path, frag = t.split("#", 1)
    m = re.fullmatch(r"L(\d+)(?:-L(\d+))?", frag)
    if not m:
        return path, None, None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return path, lo, hi


def check(repo: str, sha: str, targets: list[str], label: str) -> tuple[int, int]:
    errors = warns = 0
    seen: dict[str, int] = {}
    for t in targets:
        seen[t] = seen.get(t, 0) + 1
    print(f"\n=== {label}: {len(seen)} unique targets / {len(targets)} instances ===")
    for t in sorted(seen):
        path, lo, hi = split_target(t)
        typ = obj_type(repo, sha, path)
        if typ is None:
            print(f"  ERROR  missing path        {t}")
            errors += 1
            continue
        if lo is None:
            continue
        if typ != "blob":
            print(f"  ERROR  line range on {typ:5} {t}")
            errors += 1
            continue
        lines = file_lines(repo, sha, path)
        n = len(lines)
        if hi > n:
            print(f"  ERROR  past EOF ({n} lines)  {t}")
            errors += 1
            continue
        first = lines[lo - 1]
        if SUSPICIOUS.match(first):
            print(f"  WARN   starts mid-construct {t}")
            print(f"           L{lo}: {first[:70]!r}")
            warns += 1
    print(f"  -> {errors} error(s), {warns} warning(s)")
    return errors, warns


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", required=True)
    ap.add_argument("--repo-dir", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--old-commit", default=None)
    a = ap.parse_args()

    src = pathlib.Path(a.html).read_text()
    p = Parser()
    try:
        p.feed(src)
    except Exception as e:
        print(f"ERROR: HTML does not parse: {e}")
        return 1
    print(f"HTML parses OK ({len(src):,} bytes)")

    errors = warns = 0

    # 2. internal anchors
    internal = [h[1:] for h in p.hrefs if h.startswith("#") and len(h) > 1]
    dangling = sorted({i for i in internal if i not in p.ids})
    print(f"\n=== internal anchors: {len(set(internal))} unique ===")
    if dangling:
        for d in dangling:
            print(f"  ERROR  dangling anchor #{d}")
        errors += len(dangling)
    else:
        print("  -> all resolve")

    # 3-5. data-gh against the reviewed commit
    if p.datagh:
        e, w = check(a.repo_dir, a.commit, p.datagh, f"data-gh @ {a.commit[:11]}")
        errors += e
        warns += w

    # absolute blob links (⧖ before/after links, and any hand-written ones)
    by_sha: dict[str, list[str]] = {}
    for h in p.hrefs:
        m = GH_BLOB_RE.match(h)
        if m:
            by_sha.setdefault(m.group("sha"), []).append(m.group("target"))
    for sha, targets in sorted(by_sha.items()):
        e, w = check(a.repo_dir, sha, targets, f"absolute blob links @ {sha[:11]}")
        errors += e
        warns += w

    print(f"\n{'=' * 52}\nTOTAL: {errors} error(s), {warns} warning(s)")
    if warns:
        print("Warnings are heuristic -- eyeball each and widen or move the range.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
