---
name: maintaining-arch-strix-halo-packages
description: Use when updating, auditing, or extending this repo's package set, checking the 24-hour dependency freshness sweep, or reconciling upstream, Arch, AUR, CachyOS, or Blackcat Informatics recipe drift.
---

# Maintaining Arch Strix Halo Packages

## Overview

This repo turns a Strix Halo local AI stack into Arch packages plus a normal
local-repo workflow. The hard part is not just making builds pass. The hard
part is keeping the update story legible: which baseline each package follows,
which divergences are intentional, and where reusable source changes live.

## Use When

- update an upstream source lane
- check whether the 24-hour dependency freshness sweep is due
- reconcile drift against Arch, CachyOS, or AUR baselines
- absorb changes from Blackcat Informatics' Strix Halo recipe work
- add a new recipe-managed package
- audit patch carry or package metadata clarity
- triage ROCm inference package candidates such as MIGraphX,
  Torch-MIGraphX, FlashAttention, AITER, Triton, quantization, or profiling

## Open References Only When They Match The Task

- When reconciling a package baseline, open:
  - `docs/policies/reference-packages.md`
  - `packages/<name>/recipe.json`
  - `packages/<name>/README.md`
- When changing the package-update workflow or metadata model, open:
  - `docs/maintainers/update-workflows.md`
  - `policies/recipe-packages.toml`
- When checking the freshness cadence, open:
  - `docs/maintainers/current-state.md`
  - `docs/maintainers/update-workflows.md`
  - `policies/package-freshness.toml`
- When changing TheRock-generated package output, open:
  - `docs/architecture/therock-generator.md`
  - `docs/maintainers/therock-generator-status.md`
  - `policies/therock-packages.toml`
- When changing onboarding, publication, or repair flow, open:
  - `docs/usage/local-repo.md`
- When closing a session or handling plan, prompt, or worklog files, open:
  - `docs/policies/documentation-and-session-artifacts.md`
- When checking deferred blockers or previously verified behavior, open:
  - `docs/maintainers/current-state.md`
  - `docs/backlog.md`
- When triaging ROCm inference optimization, quantization, profiling,
  MIGraphX, Torch-MIGraphX, FlashAttention, AITER, Triton, or Composable
  Kernel package candidates, open:
  - `docs/maintainers/rocm-inference-reference.md`

## Start Discovery Here

- Start package audits at `packages/<name>/recipe.json`, then read the package
  README, then inspect the policy entry that rendered them.
- Start patch audits at the package's sibling patch files before trusting
  inline PKGBUILD shell mutations.
- Start generated-output audits at the renderer and generator sources, not at
  the generated file alone.

## Default Package-Update Loop

1. Check whether the dependency freshness gate is due before unrelated backlog
   work. Use `docs/maintainers/current-state.md` for the last completed or
   acted-on sweep, then apply `docs/maintainers/update-workflows.md`. Do not
   run `tools/check_package_updates.py` when those docs show a still-fresh
   completed sweep and no invalidating change.
   - When a freshness check reports a non-current family, assign each update
     candidate a durable disposition in
     `docs/maintainers/update-candidates.toml`: `adopted`, `tracked`,
     `rejected`, or `blocked`.
   - Do not close a refresh by only updating `policies/package-freshness.toml`.
   - Treat patch carry overlap as a reason to prioritize update review.
   - Treat absence of backend build-system changes as insufficient rejection
     evidence.
2. Identify the change lane.
   Use one of: upstream source change, baseline package change, recipe change,
   or new package.
3. Confirm the package's authoritative and advisory references.
4. Update repo policy first if the maintenance story changed.
5. Re-render generated metadata before making narrow manual edits.
6. Keep durable source changes in patch files when practical.
7. Rebuild, refresh the local repo metadata, and run the relevant smoke tests.
8. Update tracked docs if the change altered policy, workflow, or verified
   behavior.

## Guardrails

- Do not leave new maintenance knowledge only in chat history or ignored
  session files.
- Do not silently mix incompatible ROCm-family lanes.
- Do not accept a transient build workaround as the permanent package story.
- Do not freeze scoutable details in repo guidance when a current file or tool
  output can answer them more reliably.
