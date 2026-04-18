---
name: idiomatic-zsh
description: Use when writing or reviewing shell scripts in this repo unless a task specifically requires Bash or POSIX sh.
---

# Idiomatic Zsh

Default to Zsh for repo-owned shell tooling unless the script needs Bash-only
compatibility or strict POSIX `sh`.

## Rules

- Prefer Zsh built-ins, array handling, parameter expansion, glob qualifiers,
  subscripting, math expressions, and modules before external commands.
- Use `emulate -L zsh` inside functions with narrowly scoped `local` or typed
  variables.
- Use `print -P` with the standard 16 colors for operator-facing status lines.
- Keep trap cleanup explicit and avoid leaking globals across helper functions.
- Quote only where shell expansion or whitespace rules actually require it.
- If a script performs privileged package installs in this repo, pair it with
  the local workflow guidance in `rebuild-publish-install-local-packages`.

## Common Fit

- Host orchestration scripts
- Repo maintenance helpers
- Interactive operator menus

## Not Fit

- `/bin/sh` compatibility targets
- Existing Bash entrypoints that must stay Bash-compatible
