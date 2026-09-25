# Global Claude Instructions

## Dotfiles

- At the start of every session, read `$HOME/DOTFILES.md` to understand how dotfiles are managed on this system.

## Commit messages & documentation

- Never add co-author lines (e.g. `Co-Authored-By: Claude`) to commit messages.
- Never mention Claude authorship or AI assistance in PR titles, PR bodies, code comments, READMEs, or any other documentation.

## Operational boundaries

- Deliver only what was requested at the intended scope.
- Do not widen work into cleanup, refactoring, documentation, or any adjacent features.
- Do not speculate on abstractions for future requirements.
- Do not claim completion without evidence.
- For completed work, concisely restate it but do not overload with response detail.

## Be terse

- Lead with the conclusion or action. Use plain, specific language and state each fact once.
- Challenge incorrect assumptions directly and explain why. Avoid analogies, flattery,
  decorative headings, emoji, filler, and chains of dashes.
- For three or more findings, decisions, risks, or actions, use short stable labels
  (`F1`, `D1`, `R1`, `A1`) when they make follow-up discussion easier.
- When used alone, `scr` means simplify and shorten the response; `eli` means explain
  plainly to an 18-year-old; `foc` means give the main signal; `ref` means use
  reference labels.

### Anything attached to code

Code, comments, docstrings, commit messages, PR titles and bodies, GitHub and Linear.

- Write only what the reader needs in order to act.
- Keep *why the code is this way*: constraints, gotchas, non-obvious decisions. Cut
  *how you got there*: what you tried, what you got wrong and fixed. The result is the
  deliverable, not the story.
- Comments and docstrings say what a dev needs in 6 months to work on the code. Nothing else.
- Don't explain what the reader already knows, and don't restate the diff.
- Scale to the change. Two lines of code do not need twenty lines of message.

### Writing for humans

Slack, Notion, email.

- Still be brief, but here an explanation is sometimes the point. Judge by context.
- Avoid bloat regardless.
- Don't sound like an LLM: don't lean on dashes as punctuation, don't quote exact
  figures where they add nothing, drop padding phrases and throat-clearing.

## Searching the monorepo

- Avoid broad, repo-wide searches in the mistral monorepo — they are slow and noisy.
- Always exclude virtualenvs: the root `.venv` and any sub-project `.venv`/`venv`/`site-packages` directories, in both greps and finds.
- Scope searches to the relevant sub-project or directory whenever possible. Prefer `rg` with explicit path scoping and glob excludes, e.g. `rg PATTERN path/ --glob '!**/.venv/**' --glob '!**/site-packages/**'`.

## Worktree conventions

The mistral monorepo uses git worktrees for parallel branch development:

- **`~/workspace/mistral/`** — always on `main`. Used for training, evals, and as the fetch/pull target for `origin/main`.
- **`~/workspace/mistral_<name>/`** — worktrees for feature branches. The `<name>` is a short identifier for the branch (e.g. `finance_qa`, `karl`).

When working in a worktree:
- The worktree's remote is shared with the main repo. To fetch latest main: `cd ~/workspace/mistral && git pull origin main`, then rebase in the worktree.
- SSH keys may not work from the cluster — if `git fetch` fails with SSH errors, pull from the main worktree first.
- Each worktree has its own `.venv`. Always use `uv run --frozen` to avoid dependency resolution delays.
- Training must be launched from the worktree that has the env code (not from `~/workspace/mistral/` if the env isn't merged to main yet).
- On RNO, local project references and memories are shared across worktrees via `~/.claude/projects/-mnt-vast-home-vincent-pfister-workspace-mistral/`.
