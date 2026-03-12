---
name: setup-config
description: manages the config and setup of dev and system toolchains
licence: MIT
user-invocable: true
allowed-tools:
  - read_file
  - grep
  - list_directory
  - ask_user_question
---

# setup-config

This skill helps configure locally installed system or development tools.

## First step (always)

Always start by reading `~/DOTFILES.md` to understand how dotfiles are managed on this machine before making any changes.
If `~/DOTFILES.md` is missing or cannot be read, stop and ask the user where the dotfiles instructions live (or request that the file be created).

## Shell compatibility

When possible, configuration should work for both `zsh` (macOS) and `bash` (Linux).

- Prefer portable POSIX shell where feasible.
- Avoid shell-specific syntax unless necessary.
- If a change must be shell-specific, provide both variants and clearly label them (`zsh` vs `bash`).
- When editing startup files, target the appropriate files for each shell (for example `.zshrc` for `zsh`, `.bashrc` or `.bash_profile` for `bash`, depending on the system).


## Escalation

If changes require writing files or running shell commands, ask the user to approve running outside this skill’s res:wqtricted tool set, or run the changes via a separate skill/agent that includes `write_file` / `bash`.
