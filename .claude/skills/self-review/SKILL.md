---
name: self-review
description: Make a PR or a stack of PRs ready for a code owner to review — verify each layer standalone, check naming and comments for drift, cut docstring and test bloat, then write descriptions that state constraints rather than narrate the work.
---

# Self-Review Before Requesting Review

Run this before flipping a PR out of draft.

## The point of all of it

**Everything here exists to make the human reviewer's job easier.** They have limited
attention and they are the scarce resource. Spend it on decisions only a person can
judge, not on defects a second pass would have caught, not on reading around noise.
Better maintainability is a welcome side effect, not the goal.

**Nothing here is a mechanical action.** Every item below is "analyse thoroughly, then
act only where it serves that goal". Applied mechanically these rules do harm: they
delete tests that looked redundant but pinned a real edge case, rename things a reader
already knows, split a module along a seam nobody thinks in, or churn a diff so the
reviewer can no longer see what actually changed. A pass that finds nothing worth
changing is a successful pass — say so and move on.

Judgement also means weighing churn. A cleanup that improves the code slightly but
doubles the diff makes the review harder, which is a net loss. When in doubt, note it
for later rather than doing it now.

Do the passes in order. Each finds a different class of problem, and the later ones are
wasted if the earlier ones have not run.

## 1. Verify each layer standalone

A green merged branch says nothing about the PRs a reviewer actually opens.

- Run the tests **at each PR's own head**, not only at the top of the stack. A middle
  layer that uses something introduced above it passes on the merged branch and fails
  in CI.
- Run the type checker per layer too. It catches what pytest cannot: a test asserting
  an attribute on a base type, a helper whose type narrowing disappeared in a refactor.
- Expect the test count to rise monotonically up the stack. If it does not, a layer's
  tests are probably not running.
- Before blaming your diff for a red CI, check whether the same job fails on `main`,
  across several recent builds rather than one.

## 2. Confirm the change survives a real launch

Unit tests construct objects directly. Production usually does not.

- If configs round-trip through YAML, JSON or a registry at launch, test that
  round-trip. A provider missing from the registry passes every unit test and fails on
  the first real run.
- Prove a new guard test fails without its fix: break the fix, watch it go red, restore.
  A test that has never failed has not been shown to test anything.
- Check fixtures match the shape production returns. A field that is a dict of reasons
  in reality and a bool in the fixture means the test is green about the wrong thing.
- Check every new knob is reachable from where it will actually be set. A parameter
  plumbed into the object but not through the config builder is unreachable, and that
  is a defect even though everything compiles and passes.

## 3. Re-read every comment and docstring for staleness

Do this as a deliberate pass, not incidentally. Comments rot silently, and a confidently
wrong comment is worse than none: it makes a reviewer distrust the code, or worse,
trust the comment.

- Read every comment in and adjacent to the changed code, including ones you did not
  touch. Behaviour you added elsewhere can falsify a comment you never opened.
- Watch for comments that describe a limitation you have since removed, a mechanism you
  replaced, or a constant that has moved.
- **Check the claim against the code, not only against history.** Drift is the easy case.
  The harder one is a comment that was never true: it states the design someone intended
  rather than the one they shipped, and it reads exactly like a drifted one. If a
  docstring names a mechanism, find that mechanism in the code. A docstring claiming a
  phrase-matching grammar the builder does not use will have a reader confidently wrong
  about retrieval behaviour, and no test will fail.
- Docstrings that describe the *old* contract are the most dangerous, because they read
  as the intended design and a reviewer may defend them.

## 4. Check names still fit

Purpose drifts under successive fixes and refactors, including other people's. The name
chosen when the thing was introduced is often no longer what it does.

- A constant whose meaning narrowed or widened: a "default" that is now a ceiling, a
  "max" that is now a starting point.
- Functions that grew a second responsibility, or lost their original one.
- Modules whose name describes only part of what they now hold.
- Names that are still literally accurate but now misleading in context.

While here, look for defined-but-unused names. A constant nothing references is dead
weight, and if it contradicts the live one it actively misleads.

Rename only when the new name genuinely helps a reader. A rename touching many call
sites can swamp the real change; if so, note it for a follow-up.

## 5. Check the types tell the truth

A name can be right while the type lies about what it holds. Nothing else in this list
catches that, and it is the class of thing a reviewer objects to on principle rather
than by finding a bug.

- **A sum encoded as a product.** `tuple[A, None] | tuple[None, B] | None` makes every
  caller unpack both slots and assert one away. Return the union.
- **`object` / `Any` / a bare `dict` where the real type is known.** It pushes the
  knowledge to call sites as casts.
- **One container holding two namespaces**, so callers immediately separate them again.
  A dict of query placeholders that also carries request parameters means every
  consumer, and every invariant over it, needs a carve-out.

The symptom is in the tests, not the source: **repeated `cast(...)`, `isinstance` fences,
or an assertion helper that skips certain keys.** Those exist because the type is not
saying enough. Grep the test file for `cast(` before deciding this pass found nothing.

Weigh it against churn like any rename: fixing a type touches every call site, so it is
cheapest before the first consumer lands and dearest after review has started.

## 6. Consider splitting very long modules

Length alone is not a reason. Split when it makes the module easier to read:

- A long module where lengthy private helpers are interleaved with the public surface,
  so following the main flow means scrolling past machinery. Pulling helpers into a
  private sibling module often makes both halves readable.
- A module holding two things that change for different reasons and share little.
- Any file where you cannot state what it is responsible for in one sentence.

Do not split to hit a line count, and do not split along a seam that forces readers to
jump between files to follow one thought. Splitting also rewrites file paths in the
diff, which costs the reviewer; only worth it if the gain is real. If the module is
long but linear and well-ordered, leave it.

## 7. Cut the docstrings and comments

Apply the "Be terse" rules in `~/.claude/CLAUDE.md`. Cut *how you got there*: what
broke, what you measured, what you tried. Keep *why the code is this way*: constraints,
gotchas, decisions a reader would otherwise undo.

Also cut `Args:`/`Returns:` blocks that restate the signature, process narration
("verified green", "N-line delta", "found by X"), and explanations of what the reader
already knows. Doc pointers should name the file by its full in-repo path.

A twenty-line comment on a constant is almost always narrative.

**This pass covers comments you did not write**, like §3. Otherwise it silently scopes
itself to your own additions and leaves the longest blocks in the file untouched, which
are usually the oldest ones. Look for the same explanation given three times in three
places; keep one and point at it.

## 8. Factor the tests

- Repeated setup is a fixture or factory helper. Look for the same three or four lines
  opening many tests.
- Near-identical tests differing in one value are one `@pytest.mark.parametrize`.
- After moving setup into a helper, re-run the type checker: assignment inside a helper
  stops narrowing the type at the call site.
- Factor for readability, not for line count. A helper with five flags controlling what
  it builds is harder to read than the duplication it replaced.

## 9. Prune weak tests

Delete tests that restate what a stronger test already pins:

- Single-field assertions on a golden object a full-equality test covers.
- Assertions that a constant is a non-empty string of the expected shape.
- Negative substring checks structurally guaranteed to pass.
- **Two separately-named tests asserting one sentence.** Duplication across functions
  hides better than duplication inside one, because the names differ and neither looks
  redundant on its own. A parametrize row covering the same input as a standalone test
  is the common shape. Search by input, not by name.

Also delete tests **fragile for reasons unrelated to their subject**: one hard-coding an
environment-specific value fails for someone on a different cluster and teaches them to
distrust the suite.

Keep edge cases, contract pins, and anything that failed before its fix. When unsure
whether a test is weak, ask what bug it would catch. If you can name one, keep it.

## 10. Look for near-duplicate logic

Two blocks doing the same thing with different arguments are a hazard when they must
stay in step: a metric incremented beside a log line, an error counted beside a message.
Factor those to a single exit point so they cannot drift.

Do not refactor pre-existing code the PR merely touches. A reviewer will rightly ask why
unrelated error handling changed in a feature PR. Note it instead.

**The exception is the pattern the PR exists to remove.** When the change closes a footgun —
a default that hides a decision, a flag two things derive from separately — grep the same
file for other instances before shipping. Fixing one and leaving its twin is worse than
leaving both: the next reader sees the pattern addressed and assumes it is done, and a
reviewer who asked about the instance they happened to see will assume you checked for the
rest. "It was pre-existing" does not apply to the thing you are here to fix.

Fix them all, or say in the thread which ones you left and why. **If you decide to raise it
rather than fix it, raise it before you push** — an intention formed while editing is not a
message anyone received.

## 11. Check the PR contains only what belongs to it

- No unrelated files swept in: config, scratch files, another workstream's commits.
- No debris: TODOs you meant to resolve, prints, commented-out code, debug helpers.
- The change reads as one coherent unit. If it needs "and also" to describe, consider
  splitting it.

## 12. Rewrite the descriptions last

Only now, when the code is final. Per PR:

- **Why** — the problem, in one or two sentences. Never inferred from the diff.
- **Summary** — what changed, by file.
- **Reviewer guide** — which decisions deserve challenge, and what breaks if reversed.
  Not a restatement of the diff.
- **Test plan** — what ran, and what is *not* covered.

Then check the description against the final code. A description still describing a bug
you fixed presents the defect as the design, which is worse than saying nothing.
Descriptions written mid-work are usually stale by the end.

Target roughly 200 words.

## 13. Close out the review threads

Only applies on a second or later round. Cheap, and the one place where "I already handled
that" is most likely to be false.

**Ask who spoke LAST in each thread, not whether you replied in it.** A reviewer who answers
your reply leaves a thread that contains your reply, so any check for "did I respond" passes
it, and every UI renders it as a conversation you took part in. The follow-up is where the
reviewer says your fix was incomplete, so it is exactly the message worth catching.

```bash
gh api repos/{owner}/{repo}/pulls/{n}/comments --paginate
# group by (in_reply_to_id or id), sort each group by created_at,
# flag any group whose last author is not you
```

Two legitimate reasons a reviewer has the last word, and they need separating:

- They answered a point and expect nothing back, or are deliberately holding a thread open
  as an owner marker for later work. Reply so it is on the record, change nothing.
- They told you the fix missed something. That is unaddressed review, whatever the thread
  looks like.

**Verify the claim before acting on either.** A follow-up that downgrades the reviewer's own
finding is still a claim: check it. And when the follow-up is right, check the code rather
than the comment — the usual shape is a docstring left asserting the behaviour you just
changed, three lines from an inline comment that now contradicts it.

## 14. Ship

- Mark ready bottom-up, one at a time, each only after the one below is green.
- Name who must approve. A code-owner or group gate is often the long pole.
- State plainly what is still unverified. "Nothing here proves the query is executable
  against a live index" is worth more than a clean-looking test plan.

## Working on a stack

The tension: **validation is per layer, cleanup is naturally stack-wide.** A dedup or
rename spotted at the top of the stack usually belongs in the layer that introduced the
code, not where you noticed it.

- Land each cleanup in the layer that owns the code, then merge upward. Fixing it only
  at the top leaves the lower PRs — the ones reviewed first — carrying the flaw, and the
  reviewer reasonably assumes you did not notice.
- **This one is easy to get wrong even knowing the rule**, because passes 3-9 are done
  while sitting on the top branch, where every file is visible and one commit is natural.
  So check explicitly: for each PR, `git diff --stat <its base> <its head>` and confirm
  every file listed is one that PR introduces or legitimately wires up. A file owned by
  a lower layer appearing in a higher PR means a cleanup landed in the wrong place.
- To redistribute afterwards, per owning branch:
  `git show <cleanup-sha> -- <path> | git apply --3way`, commit, then merge upward. The
  upper layers absorb it without conflict because both sides reach identical content.
  Re-run the per-layer tests: the top layer's count should be unchanged, which is what
  proves the move preserved content rather than dropping some.
- After any cross-layer change, re-run the per-layer checks from §1. A helper factored
  out at layer 3 and used at layer 2 compiles fine merged and breaks standalone.
- Some cleanups genuinely span layers, such as a helper two PRs both duplicate. Put it
  in the lower one and let the upper adopt it on merge.
- Resist rewriting a lower PR late purely for tidiness. It invalidates review already
  done on it. Weigh the improvement against that cost.

### Stack mechanics live elsewhere

How to build, base, number, rebase and land a stack is the `stack-pr` skill in
`.agents/skills/stack-pr`.

Three things from it that change what you *check* rather than what you do:

- Each PR should show only its own increment. Verify by listing each PR's files; if a
  PR shows its parent's files, the bases are wrong and every reviewer sees the wrong
  diff.
- Landing is bottom-up, so a lower PR is reviewed and merged before the ones above are
  final. That is what makes "fix it in the layer that owns it" matter rather than being
  a nicety.
- If the titles are numbered, `(N/N)` tells a reviewer the stack is complete. Before
  using it, decide what is deliberately out of scope and say where it went, or the
  number is a claim you cannot keep.
