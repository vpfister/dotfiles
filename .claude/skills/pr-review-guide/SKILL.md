---
name: pr-review-guide
description: Use when asked to understand, walk through, tour, onboard onto, or high-altitude review a large or unfamiliar pull request — especially one too big to read linearly (thousands of lines, dozens of files), or when re-reading a PR whose branch has moved since last time. Produces a served, commit-pinned HTML walkthrough with verified deep links.
---

# PR review guide

Turn a PR that is too big to read into a timed, navigable walkthrough — a single
self-contained HTML page, served, where every path and snippet deep-links to the exact
lines on GitHub.

**The output is a reading aid for a human, not a review verdict.** It explains what the
PR does and where to look. Findings are a by-product of reading carefully, and they
belong in the last section, phrased as questions for the author.

## When to use

- "walk me through PR X" / "give me a tour of" / "help me understand this PR"
- A PR too large to read linearly, or in a subsystem you don't know
- Onboarding someone else onto a PR
- Re-reading a PR you toured before, after the author pushed more commits

**Not for:** small diffs you can just read; a line-by-line review verdict (use
`/review`); your own working diff (use `/code-review`).

## Inputs

A PR number (assumes `mistralai/mistral`) or a full PR URL. Nothing else.

## The one rule

**Never state a line number, a path, or a claim about the code that you have not
resolved against the actual commit.** A guide's whole value is that the reader can
click and land on the right thing. A confidently wrong line number is worse than no
link. The verifier exists because eyeballing this fails — on a real run it caught 12
mis-inferred ranges and an off-by-one that had already survived a manual check.

## Workflow

### 1. Survey before reading

```bash
S=~/.claude/skills/pr-review-guide/scripts
python3 $S/pr_survey.py <number-or-url>
```

Gives you: metadata, head SHA, commit list, additions bucketed into
generated/lock/real, identical-line-count clusters, and the 15 largest files.

**Lead with this in the guide.** Big PRs are usually mostly generated: a "100K line"
PR was 87% sweep YAML and 7% hand-written. Telling the reader the real size in the
first screen changes how they approach everything after.

Cluster detection is a hint, not proof — N files with identical line counts are
usually machine-emitted, but check before saying so.

### 2. Fetch the branch, don't check it out

```bash
cd ~/workspace/mistral && git fetch origin <headRefName>
git show origin/<headRefName>:<path>      # read any file
```

A worktree is unnecessary for reading and costs a full checkout. **Pin everything to
the full head SHA**, never the branch name — the branch will move.

Check `git worktree list` for a stale worktree of a *related* branch (e.g. the branch
the PR was ported from). If one exists, warn the reader off it explicitly and say how
far behind it is.

### 3. Read along the data path

Read in the order the data flows, not the order the file tree lists. Typical spine:
input format → transform → storage schema → serving → integration points. Anchor each
stop on the file a reader would open.

Batch reads with `git show` in parallel calls. Read whole small files; head the long
scripts. Prioritise: schema/migration files, anything named `*_core`, `*_fields`,
`models`, the module docstrings of scripts, and README/tutorial files (they state
intent, which you then check against the code — the gap between them is where the good
findings live).

### 4. Write the body fragment

Write only `src/body.html` — the template owns all CSS, JS, nav and scrollspy. Never
hand-write the chrome; that is what the builder is for.

Each section:

```html
<h2 id="s4" data-mins="4" data-group="Ingestion path">
  <span class="num">4</span>The Vespa schema</h2>
<p class="budget">≈ 4 min · why this file matters</p>

<div class="paths">
  <div><span class="k">→ </span><span data-gh="path/to/file.py">path/to/file.py</span></div>
</div>

<span class="codelabel">
  <span data-gh="path/to/file.py#L53-L63">file.py — what this shows</span>
  <span class="lines">L53–63</span>
</span>
<pre class="hl"><code class="language-python">...escaped code...</code></pre>
```

`data-gh="path"` or `data-gh="path#L12-L34"` becomes a permalink at build time. Put it
on inline `<code>` for symbol mentions too — the reader should be able to click any
name you use.

Escape `<`, `>`, `&` inside `<pre>`. Generic types (`tensor<int8>`, `list[dict]`) break
the page otherwise.

Available blocks: `.callout.warn` (problem), `.callout.note` (aside), `.callout.ok`
(fixed/resolved), `.paths`, `.ascii` (pipeline diagrams), `.codelabel + pre`, tables,
`.del` (struck-through removed names).

Close each section with `<a class="top" href="#">↑ top</a>`.

### 5. Build

```bash
python3 $S/build_guide.py --body src/body.html --out <dir>/index.html \
  --repo mistralai/mistral --commit <full-40-char-sha> \
  --h1 "PR #NNNNN — Title" --title "PR #NNNNN — Guided Tour (30 min)" \
  --brand "PR #NNNNN" --brandsub "subject — 30 min tour" \
  --subtitle-file src/subtitle.html --banner-file src/banner.html \
  --navnote-file src/navnote.html --target-mins 30
```

The sidebar is **derived** from the `<h2>` tags, so it cannot drift. `--target-mins`
warns if the per-section budgets don't sum to the length you advertised.

### 6. Verify — not optional

```bash
python3 $S/verify_links.py --html <dir>/index.html \
  --repo-dir ~/workspace/mistral --commit <full-sha>
```

Errors (missing path, range past EOF, dangling anchor) **must** be zero.

Warnings say a range's first line looks mid-construct — a blank line, a closing
bracket, a docstring. Eyeball every one. Most are real off-by-ones where you pointed
at a docstring instead of the `class`/`def` line. A few are intentional (you meant to
quote the module docstring); leave those.

When a block's exact end is unclear, prefer a slightly wide range over a guessed one.
Landing the reader a few lines early is fine; landing them in the wrong function is not.

### 7. Serve and report

```bash
bash $S/serve_guide.sh <dir> 20788
```

Prints the routable URL. Ports below 20000 are reserved on cluster nodes. The server
reads from disk per request, so rebuilding picks up automatically — no restart needed.
Note the node IP can change if the login pod restarts; re-run the script to get the
current URL.

Put the guide somewhere durable — `~/gh/vpfister/mistral-work/tours/pr<NNNNN>/` — and
keep `src/` next to `index.html` so it can be rebuilt.

**In your reply**, give the URL, the real-vs-headline size, a one-line structure
summary, and the findings in prose. Don't make the human open the page to learn
whether anything is wrong.

## Re-running after the branch moves

```bash
python3 $S/pr_survey.py <number> --since <sha-you-last-pinned> --repo-dir ~/workspace/mistral
```

Then:

1. `git diff <old> <new> -- <path>` every MODIFIED file you cited. Renames and deletions
   silently invalidate whole sections.
2. Re-check each earlier finding against the new head and say which are fixed, partly
   fixed, still open, and what's new. **A scorecard table is the most valuable thing in
   a re-run** — it tells the reader where the PR is moving.
3. Rebuild with the new `--commit`. Re-pin everything; don't leave stale links.
4. For anything the cleanup removed that mattered, add a `⧖` before/after link:
   `<a class="oldlink" href="https://github.com/OWNER/REPO/blob/<old-sha>/path#L1-L2">BEFORE — …</a>`.
   `verify_links.py` checks these against their own SHA automatically.

Read the commit *messages*. On a real run, one said "fix: broken int8 quantization" and
pointed straight at a live data-corruption bug — a duplicated field builder writing raw
floats into an int8 field. That became the most useful section in the guide.

## Writing the findings section

- Order by how badly it would bite someone, not by severity label.
- Every finding links to the line that proves it, so the human can paste it into a PR
  comment and check it in one click.
- Separate "this is wrong" from "I don't understand why this is so". Phrase the latter
  as a question for the author.
- Say plainly when something should not block the merge.
- Compare docs against code. Nearly every real finding on the example run came from
  that gap: a README documenting a tool that didn't exist, a tutorial advertising
  two-phase ranking that had no second phase, a deleted deprecation note that was the
  only explanation for an orphaned consumer.

## Common mistakes

| Mistake | Consequence |
|---|---|
| Pinning to the branch, not a SHA | Every link rots on the next push |
| Inferring line ranges from a grep of `def` | Ranges start mid-construct; verifier warns, believe it |
| Hand-writing nav alongside sections | Drifts; let the builder derive it |
| Trusting the headline diff size | You budget the tour wrong and scare the reader |
| Skipping `verify_links.py` because it "looks fine" | It caught an off-by-one that survived manual review |
| Unescaped `<` in a `<pre>` | Page silently mangles from that point on |
| Burying findings in the page only | The human wanted the answer in the reply |

## Files

| Path | Purpose |
|---|---|
| `scripts/pr_survey.py` | Metadata, bucketed sizes, generated-file clusters, churn `--since` |
| `scripts/build_guide.py` | Body fragment + template → page; derives nav from `<h2>` |
| `scripts/verify_links.py` | Anchors, paths, ranges, mid-construct heuristic |
| `scripts/serve_guide.sh` | Serve on a free port, print routable URL |
| `assets/template.html` | All CSS/JS: light+dark, scrollspy, `data-gh` → permalink |

Run any script with `--help`.
