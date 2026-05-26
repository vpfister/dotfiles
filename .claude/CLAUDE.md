# Global Claude Instructions

## Dotfiles

- At the start of every session, read `$HOME/DOTFILES.md` to understand how dotfiles are managed on this system.

## Commit messages & documentation

- Never add co-author lines (e.g. `Co-Authored-By: Claude`) to commit messages.
- Never mention Claude authorship or AI assistance in PR titles, PR bodies, code comments, READMEs, or any other documentation.

## Worktree conventions

The mistral monorepo uses git worktrees for parallel branch development:

- **`~/workspace/mistral/`** — always on `main`. Used for training, evals, and as the fetch/pull target for `origin/main`.
- **`~/workspace/mistral_<name>/`** — worktrees for feature branches. The `<name>` is a short identifier for the branch (e.g. `finance_qa`, `karl`).

When working in a worktree:
- The worktree's remote is shared with the main repo. To fetch latest main: `cd ~/workspace/mistral && git pull origin main`, then rebase in the worktree.
- SSH keys may not work from the cluster — if `git fetch` fails with SSH errors, pull from the main worktree first.
- Each worktree has its own `.venv`. Always use `uv run --frozen` to avoid dependency resolution delays.
- Training must be launched from the worktree that has the env code (not from `~/workspace/mistral/` if the env isn't merged to main yet).
- Skills and memories are shared across worktrees via `~/.claude/projects/-mnt-vast-home-vincent-pfister-workspace-mistral/`.
