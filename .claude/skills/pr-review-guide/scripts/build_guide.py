#!/usr/bin/env python3
"""Assemble a PR review guide page from a body fragment + the shared template.

The sidebar nav is DERIVED from the body's <h2> tags, so it can never drift out of
sync with the sections. Body sections must look like:

    <h2 id="s3" data-mins="4" data-group="Ingestion path">
      <span class="num">3</span>Extract and chunk</h2>

Usage:
  build_guide.py --body body.html --out DIR/index.html \
      --repo mistralai/mistral --commit <full-sha> \
      --h1 "PR #27188 - Pretraining Websearch" \
      --brand "PR #27188" --brandsub "30 min tour" \
      --subtitle-file sub.html --banner-file banner.html --navnote-file note.html

Prints a summary (sections, total minutes, link count) and exits non-zero if the
body is malformed.
"""

import argparse
import html
import pathlib
import re
import sys


TPL = pathlib.Path(__file__).resolve().parent.parent / "assets" / "template.html"

H2_RE = re.compile(
    r'<h2\s+id="(?P<id>[^"]+)"(?P<attrs>[^>]*)>(?P<inner>.*?)</h2>', re.S
)
ATTR_RE = re.compile(r'data-(?P<k>mins|group)="(?P<v>[^"]*)"')
NUM_RE = re.compile(r'<span class="num">.*?</span>', re.S)
TAG_RE = re.compile(r"<[^>]+>")


def read(p: str | None) -> str:
    return pathlib.Path(p).read_text() if p else ""


def parse_sections(body: str) -> list[dict]:
    out = []
    for m in H2_RE.finditer(body):
        attrs = dict(
            (a.group("k"), a.group("v")) for a in ATTR_RE.finditer(m.group("attrs"))
        )
        title = TAG_RE.sub("", NUM_RE.sub("", m.group("inner"))).strip()
        title = html.unescape(title)
        out.append(
            {
                "id": m.group("id"),
                "title": title,
                "mins": attrs.get("mins", ""),
                "group": attrs.get("group", ""),
            }
        )
    return out


def build_nav(sections: list[dict]) -> str:
    lines, group, open_ol = [], None, False
    for s in sections:
        if s["group"] != group:
            if open_ol:
                lines.append("  </ol>")
            group = s["group"]
            if group:
                lines.append(f'  <div class="sep">{html.escape(group)}</div>')
            lines.append("  <ol>")
            open_ol = True
        badge = f'<span class="t">{s["mins"]}′</span>' if s["mins"] else ""
        lines.append(
            f'    <li><a href="#{s["id"]}">'
            f'<span>{html.escape(s["title"])}</span>{badge}</a></li>'
        )
    if open_ol:
        lines.append("  </ol>")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--commit", required=True, help="full 40-char sha")
    ap.add_argument("--h1", required=True)
    ap.add_argument("--brand", default="")
    ap.add_argument("--brandsub", default="")
    ap.add_argument("--title", default="", help="<title>; defaults to --h1")
    ap.add_argument("--subtitle-file", default=None)
    ap.add_argument("--banner-file", default=None)
    ap.add_argument("--navnote-file", default=None)
    ap.add_argument(
        "--target-mins", type=int, default=None,
        help="advertised tour length; warns if data-mins do not sum to it",
    )
    a = ap.parse_args()

    if len(a.commit) != 40 or not re.fullmatch(r"[0-9a-f]{40}", a.commit):
        print(f"ERROR: --commit must be a full 40-char sha, got {a.commit!r}")
        return 2

    body = pathlib.Path(a.body).read_text()
    sections = parse_sections(body)
    if not sections:
        print("ERROR: no <h2 id=...> sections found in body")
        return 2

    missing = [s["id"] for s in sections if not s["mins"]]
    if missing:
        print(f"WARNING: sections without data-mins: {', '.join(missing)}")

    page = TPL.read_text()
    subs = {
        "__TITLE__": html.escape(a.title or a.h1),
        "__BRAND__": a.brand or html.escape(a.h1),
        "__BRANDSUB__": a.brandsub,
        "__NAV__": build_nav(sections),
        "__NAVNOTE__": read(a.navnote_file).strip(),
        "__H1__": a.h1,
        "__SUBTITLE__": read(a.subtitle_file).strip(),
        "__BANNER__": read(a.banner_file).strip(),
        "__BODY__": body,
        "__GHBASE__": f"https://github.com/{a.repo}/blob/{a.commit}/",
    }
    for k, v in subs.items():
        page = page.replace(k, v)

    left = [m for m in re.findall(r"__[A-Z]+__", page)]
    if left:
        print(f"ERROR: unsubstituted placeholders remain: {sorted(set(left))}")
        return 2

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)

    total = sum(int(s["mins"]) for s in sections if s["mins"].isdigit())
    nlinks = body.count("data-gh=")  # body only; the template's JS mentions it too
    print(f"wrote {out}  ({len(page.encode()):,} bytes)")
    print(f"  sections   : {len(sections)}  (~{total} min total)")
    print(f"  gh links   : {nlinks} instances")
    if a.target_mins and total != a.target_mins:
        print(
            f"  NOTE       : budgets sum to {total} min but you advertised "
            f"{a.target_mins} -- retitle or rebalance data-mins"
        )
    print(f"  pinned to  : {a.repo}@{a.commit[:11]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
