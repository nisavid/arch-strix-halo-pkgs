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
- When beginning repo work or closing a development arc, enforce the 24-hour
  dependency freshness sweep before unrelated backlog work. First check
  `docs/maintainers/current-state.md` for the last completed or acted-on sweep,
  then apply the due-state rules in `docs/maintainers/update-workflows.md`. Do
  not run `tools/check_package_updates.py` when those docs show a completed or
  acted-on sweep less than 24 hours old and no package policy, package
  directory, checker logic, or relevant source metadata change invalidates it.
  When the gate is due, use the checker's cache-aware
  `--fail-on actionable` mode, and treat actionable or failed statuses as work
  to triage before moving on. When the checker reports any non-current family,
  stop for candidate disposition. Do not close a refresh by only updating
  `policies/package-freshness.toml`.
  Each candidate must be adopted, tracked, rejected, or blocked in
  `docs/maintainers/update-candidates.toml`, and active tracked candidates must
  stay visible in `docs/backlog.md`.
- When package source refs, patches, build flags, dependency metadata, install
  layout, generated outputs, service/config files, CLI/API behavior, or runtime
  contracts change, derive the affected validation set before PR or closeout.
  Final and PR summaries must distinguish source updated, package built,
  deployed/installed, installed-smoked, and live-scenario validated states. If
  any required gate remains open, say so before describing the branch as ready.
- Start new repo work from a topic branch in a separate worktree. Do not commit
  directly on `main`; `main` is the protected branch, so push topic branches
  and merge through GitHub pull requests.
- Close out development branches through GitHub pull requests. Push the branch,
  open a PR, follow up on review comments and failing checks, and merge only
  through the protected-branch flow.
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
- When troubleshooting ROCm inference behavior, quantization, profiling,
  MIGraphX, Torch-MIGraphX, FlashAttention, AITER, Triton, Composable Kernel,
  or vLLM optimization references, read:
  - `docs/maintainers/rocm-inference-reference.md`

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
