---
name: notes
description: Use when you have learned something another session would benefit from — a tool's real usage, a trap, a procedure that works, how an environment actually behaves. Covers writing and amending shared notes in the vpfister/mistral-work knowledge base, the tutorial-versus-memory distinction, reading the index before writing to avoid duplicating or contradicting existing notes, and the spool fallback when git signing is unavailable. Also use when you are asked to extract a lane's knowledge into notes, or when you find an existing note that is wrong.
---

# Shared notes — the fleet knowledge base

`notes/` in **`vpfister/mistral-work`** (private) is the fleet's shared knowledge base.
Anything you write there is read by every other session. Your own memories are not.

## 1. Memory or note? Get this right first

| | memory | note |
|---|---|---|
| audience | you | everyone |
| tense | what **was done** | what the next person **should do** |
| content | commands run, errors hit, results measured | usage guide, procedure, trap, how a thing behaves |
| lifetime | your session | indefinite |

**The test: if the reader cannot act on it without knowing your history, it is a memory.**

Most findings have **both halves** and should be written to both places:

- **note**: "Lock from the repo root with `uv --directory <project> lock`, then judge by
  `python tools/pre_commit_hooks/check_uv_locks.py`. Do not grep the lock for a hostname —
  `origin/main` already contains 2,536 proxied URLs."
- **memory**: "This cost two cycles on buildkite 294651; the subproject-generated lock
  differed by 916 lines."

Writing only the memory is how the fleet loses knowledge. Three lanes independently
rediscovered the stale-worktree rule that way.

## 2. Read before you write

```bash
cd ~/gh/vpfister/mistral-work && git pull --rebase
# remote: git@github-mistral-work:vpfister/mistral-work.git (scoped deploy key,
# works even when the forwarded agent is unavailable)
cat notes/INDEX.md        # what already exists
grep -rl '<your topic>' notes/   # INCLUDING the notes you wrote yourself
```

**Grep your OWN notes too, do not rely on recalling them.** You remember a note by *why
you wrote it*; what ended up in it is usually more. Observed: a lane described its own
runbook as covering "the operational half", and it already carried four of the six items
the lane was about to write again.

Then one of:

- **Nothing covers it** → write a new note.
- **A note covers it** → amend that note rather than adding a second one.
- **A note is WRONG and you have first-hand knowledge** → correct it, **and tell the
  archivist**. If both your lane and `archivist` are listed in
  `~/.claude/fleet/synapse-routes.json`, post to `archivist` on the `fleet` Synapse
  board. Otherwise use
  `~/.claude/fleet/fleet-send.py archivist --from <your-lane> --subject '...' --body '...'`
  and issue the `SendMessage` it prints.

That last case matters. You are a better contradiction detector than the archivist for
your own domain, because your knowledge is first-hand. A silent overwrite hides a
disagreement that may need arbitration; a flagged correction does not.

**"Do not write it on my authority" is a PROVENANCE constraint, not a veto.** If you are
asked for something you only half-remember, say so and decline to back it — that is the
right answer and it is expected. The claim can still be published by whoever re-verifies
it first-hand, with the provenance being theirs, not yours. Declining to vouch and
objecting to the content are different acts; say which one you mean.

## 2b. Search before you write

```bash
python3 ~/gh/vpfister/mistral-work/tools/notes-search.py "<what you are about to write about>"
```

Ranks over title, tags, description, INDEX hook, headings and body. Reads the files live,
so there is no index to rebuild and nothing that can go stale against the notes.

```bash
notes-search.py "dead index returns empty"   # free text
notes-search.py --tag ocr                    # exact topical membership
notes-search.py --path ops/evals             # browse one area
notes-search.py "shard" --body               # show the matching body lines
```

It exits 1 and says so on no match, rather than returning weak hits. **A no-match is not
proof of absence** — your vocabulary may differ from the note's. Read `INDEX.md` (one hook
per note) before concluding nothing covers your subject. That is not hypothetical: a
coverage survey over `ops/vespa` scored two notes as absent — they already carried the
material, in different words. It was caught only because someone read the notes instead of
trusting the ranking.

## 3. What belongs in a note

**A note points at where the live data lives and how to read it. It does not copy the data
in.** Pointers stay true; copies are wrong the next time anything runs.

| copy — wrong within days | pointer — still true in six months |
|---|---|
| "BLC holds 34,219,738 docs." | "For a true doc count, query the query pod: `documents_active` in Prometheus overcounts by ~13x." |
| "FAB arm F 928 scored 0.8093." | "FAB evals run at defaults (50 turns, no effort override); deviating is worth ±8 points, so always state the config." |

**Admission test: if the value expires with the date, it is not a note.** A point-in-time
measurement belongs in your memory or a filing. Its note form is the durable claim, with
the run and date as provenance in the body.

## 4. Writing

All repo conventions — filename, front matter (`date`, `title`, `tags`, `description`,
plus optional `path`, `deprecation`, `archived`), links, headings — are defined once in
**`mistral-work/AGENTS.md`**. Read it; do not reinvent the format here.

Fleet-specific rules on top of it:

- **One file per note**, named `<topic>.md`, not `<lane>-<topic>.md`. Notes are owned by
  the subject, not by whoever wrote them.
- **Storage is flat.** Do not create folders. Use the optional `path:` front matter for
  browsing hierarchy — a note can declare several paths, and files never move, so links
  never break.
- **Never delete a note.** Set `archived: true` and state why on the first line of the
  body, linking the replacement.
- **Commit straight to `main`.** No branch, no PR. Notes have no dependencies and no
  build; a branch buys nothing and costs a round trip.
- `git pull --rebase && git push`. File-per-note means conflicts are near-zero; a push
  race is resolved by retrying.
- **Verify against the REMOTE, not the exit code.** Unconditionally, one command:

  ```bash
  git log --oneline -1 -- notes/<file>          # is it actually committed?
  git ls-remote origin main                     # compare to local HEAD
  ```

  A real case: `git add` silently staged nothing, `git commit` said "nothing added to
  commit" — and that line was piped into `tail -3`, which ate it. `git push` with nothing
  to push **exits 0**, so `&& echo PUSHED` printed. Three commands ran, all "succeeded",
  and the note sat untracked for days. **An exit code measures whether the command ran,
  not whether your note is in the repo.**
- **Write or amend at least one note per task.** If a task taught you nothing
  transferable, say so and move on — but that should be rare.

## 5. When git signing is down

The laptop relay fails regularly and has been in three different states in one day. Do
not lose the note.

```bash
mkdir -p /mnt/vast/shared/vincent.pfister/kb-inbox
cp mynote.md /mnt/vast/shared/vincent.pfister/kb-inbox/
```

Always writable, no signing, no races. The archivist drains it on its next sweep. Same
pattern as `~/.claude/fleet/requests/`.

**Probe before concluding you are blocked** — `~/.claude/fleet/fleet-infra-check.py`, and
for a push the decisive test is `git ls-remote`, which costs a second. An agent that reads
`UP` only proves it will *list* keys, never that it will *sign*.

## 6. What makes a good note

**Verbosity rules first: notes fall under "Be terse" in `~/.claude/CLAUDE.md` ("anything
attached to code") and the `sp` output style. Both govern. Write only what the reader
needs in order to act; no justification, no preamble, no story.**

A note that reads like a report of work done is the wrong shape:

> Bad: "We initially assumed the emitter was fine and spent a day chasing the validator.
> After ruling out three causes we found that `$defs` is dropped unless there is a
> root-level `$ref`."
>
> Good: "`$defs` is dropped unless the property has a ROOT-level `$ref`, so
> `list[Model] | None` loses its definitions and the pointer dangles."

Same fact, no story. The day of chasing is a memory.

- **Lead with the rule**, not the story. The reader wants to act.
- **Headings, `title:` and `description:` are READ ALONE, so a hedge in the body does not
  reach that reader.** Leading with the rule puts your most compressed claim exactly where
  no qualification can follow it. The test: **would this heading still be true if the
  paragraph under it were deleted?** A real failure — "Corroborated on different data" over
  a paragraph explaining that the second run shared the first's provenance. Delete the
  paragraph and the heading is simply false.
- **For a table, that test does not work and you need a different one.** Delete the cells
  and a column header is not false, it is empty. **A table whose every cell is accurate can
  still assert a false relationship through its column headers, and the accuracy of the
  cells is what stops anyone checking.** So ask: **do the cells support the comparison the
  header sets up?** Two ways they do not: the rows were not all measured on the same thing,
  or they were, and it is not the thing the header names. A real one — a column headed
  `US (sec_chunk_32k)` over correct cells implied
  two arms were incompatible; the implication was false and stood for nineteen days,
  including being read back and reported as a blocker by its own author.
- **An INDEX line and a `description:` field are the note compressed to one sentence and
  promoted to the position a reader trusts most. Write only what the note proves. A
  qualifier dropped for length becomes an assertion.** They read as summaries, which is
  why nobody checks them — and why a withdrawn figure survives longest there.
- **State what is verified and what is assumed.** "Measured on X" and "believed, not
  checked" are different claims and the difference outlives you.
- **Cite the ref or SHA** anything was checked against. A code claim with no ref rots
  silently; every worktree on this machine is hundreds to thousands of commits behind.
- **No dates or transient facts in the rule itself** — "as of today", "while Maxime is
  away". Those belong in the body, dated.
- **A provenance date is the date of the MEASUREMENT, never the date you were told.** A
  session running for days will write "today" about a measurement from last week, and the
  writer cannot catch it by re-reading — inside the session there are no gaps. When a lane
  reports a figure with a relative date, get the absolute one before writing it down.
  Stamping it with the date you received it manufactures a provenance claim that outlives
  the conversation and reads as verification. This has happened: one drifted "today"
  became a false `re-checked` line in **two** notes, and because both agreed, comparing
  them found corroboration rather than the error. Only the source saying "I did not do
  that" exposed it.
- **Cut the narrative.** What you tried and what went wrong is memory. The result is the
  note.

## 7. The archivist

A lane owns `notes/`: dedupe, contradiction checks, splitting and merging, archiving
superseded notes, owning the `path:` vocabulary, and maintaining `INDEX.md`. It sweeps on
new commits and does housekeeping daily.

It will rewrite, merge or split what you write. That is its job and not a criticism.
Nothing you commit is blocked waiting for it.
