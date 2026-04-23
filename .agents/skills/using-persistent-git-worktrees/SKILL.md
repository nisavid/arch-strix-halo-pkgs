---
name: using-persistent-git-worktrees
description: Use when starting nontrivial repo work in a dedicated git worktree, creating or moving a coding worktree, or handling sandbox friction around sibling worktree setup.
---

# Using Persistent Git Worktrees

## Overview

For this repo, the default persistent coding worktree path is a sibling `.wt`
directory beside the main clone:

```text
/path/to/repo
/path/to/repo.wt/<branch-or-task>
```

Use that layout for nontrivial feature, packaging, and tooling work unless the
user or repo docs explicitly require a different persistent location.

## Use When

- starting substantial work that should not reuse the active checkout
- creating a new branch worktree for this repo
- moving a wrongly placed persistent worktree into the canonical sibling
  location
- auditing or handing off repo worktrees
- resolving sandbox friction around sibling worktree creation

## Directory Policy

- Default to `<repo>.wt/<branch-or-task>`.
- Report the full worktree path and branch name after creation.
- Treat `/tmp`, cache roots, and other automatically cleaned directories as
  disposable-only locations. Do not place persistent coding worktrees there.

## Sandbox And Approval Policy

If the sibling `.wt` path or the shared `git worktree` metadata writes need
approval because they sit outside the writable roots, request escalation.
Do not reroute persistent branch work to `/tmp` just because it is writable.

## Creation Pattern

For `/path/to/repo` and branch `feature-x`:

```bash
mkdir -p /path/to/repo.wt
git worktree add /path/to/repo.wt/feature-x -b feature-x
cd /path/to/repo.wt/feature-x
git worktree list --porcelain
git status --short
```

If the branch already exists, omit `-b`:

```bash
git worktree add /path/to/repo.wt/feature-x feature-x
```

When the task depends on repo submodules, initialize them from inside the new
worktree before treating missing content as unavailable:

```bash
git submodule update --init --recursive
```

## Context Checks

At the start and end of substantial work, and before switching focus, run:

```bash
git worktree list --porcelain
git status --short
```

When the active worktree differs from the main checkout, report which path is
active.

## Moving Wrongly Placed Worktrees

When a persistent worktree already exists in the wrong location, prefer:

```bash
git worktree move <old-path> <new-path>
```

If `git worktree move` cannot move it and the worktree has no uncommitted
changes, remove and recreate it in `<repo>.wt/`. If it has uncommitted work,
stop and ask before moving or recreating it.

## Guardrails

- Do not switch the user's main checkout away from `main` just to start work.
- Do not copy worktrees with `cp -a`.
- Do not leave the active path ambiguous in a handoff.
