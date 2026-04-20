# AGENTS.md

This repo is the canonical packaging workspace for a Strix Halo local inference
stack on Arch. Treat it as a packaging and policy repo first.

Your job is not to make a build pass once. Your job is to leave behind package
logic, patch carry, and documentation that a fresh agent can audit and update
without chat history.

## Follow These Rules

- Never commit private filesystem paths, private hostnames, private network
  addresses, machine-specific IDs, tokens, or keys.
- When a task needs upstream recipe or reference source from submodules, update
  submodules recursively in the active worktree before treating missing source
  as unavailable.
- Keep durable project documentation under `docs/`.
- Keep package-specific maintenance context in `packages/*/README.md` and
  `packages/*/recipe.json`.
- Put session-scoped prompts, specs, plans, scratch notes, and handoff material
  in ignored locations such as `.agents/session/` or `docs/worklog/`.
- Extract durable insight from session artifacts into tracked docs before
  ending the work.
- Delete session-only inputs once their durable content has been extracted.
- Do not consider a work plan finished until its session-only inputs are gone.
- Start nontrivial feature, packaging, or tooling work in a dedicated branch
  worktree when the active checkout has existing changes or the task spans
  multiple files and verification steps. Use a sibling
  `<repo>.wt/<branch-or-task>` directory by default, and do not switch the
  user's active checkout to a different branch just to start new work.
- Use Conventional Commits. A scope is preferred, not required, when it says
  something useful that would otherwise take more room in the summary. Use
  lowercase scopes, and use slashes for nested scopes such as `docs/usage` or
  `packages/lemonade-server`.
- Bare `pytest` is the repo-owned test suite and should collect only `tests/`.
  Run package-local tests by explicit path, such as
  `pytest tests packages/<name>/tests -q`, when a package change needs them.
- When you make a focused repo change and verify it, commit it before your
  final response unless the user asked you not to commit, verification failed,
  the scope is ambiguous, or unrelated worktree changes make a clean commit
  unsafe. Do not leave a verified change as an uncommitted handoff item.

## Read These Documents When Their Trigger Applies

- When changing TheRock split-package generation, manifest ownership, or output
  shape, read:
  - `docs/architecture/therock-generator.md`
  - `docs/maintainers/therock-generator-status.md`
- When changing package baselines, recipe metadata, update policy, or patch
  provenance, read:
  - `docs/policies/reference-packages.md`
  - `docs/maintainers/recipe-inputs.md`
  - `docs/maintainers/update-workflows.md`
- When changing local-repo publishing, installation, repair, or onboarding
  flow, read:
  - `docs/usage/local-repo.md`
- When ending a session or deciding whether notes belong in Git, read:
  - `docs/policies/documentation-and-session-artifacts.md`
- When checking verified behavior, deferred blockers, or near-term follow-up
  work, read:
  - `docs/maintainers/current-state.md`
  - `docs/backlog.md`

## Start Scouting Here

- When auditing or updating one package, start with:
  - `packages/<name>/recipe.json`
  - `packages/<name>/README.md`
  - `policies/recipe-packages.toml`
- When tracing generated TheRock output, start with:
  - `tools/render_therock_pkgbase.py`
  - `generators/therock_split.py`
  - `policies/therock-packages.toml`
- When tracing generated recipe-package output, start with:
  - `tools/render_recipe_scaffolds.py`
  - `policies/recipe-packages.toml`
- When auditing patch carry, start with:
  - `docs/patches.md`
  - patch files beside the affected package
  - only then any remaining PKGBUILD shell edits
