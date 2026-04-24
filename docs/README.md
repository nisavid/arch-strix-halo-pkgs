# Documentation Index

Use this index to choose the smallest document that answers your question. The
repo has user docs, maintainer docs, package reference, and state ledgers; each
serves a different reader.

## If You Want To Install Or Operate The Stack

- [Local Repo Usage](usage/local-repo.md) explains how to publish `repo/x86_64`,
  enable the local pacman repo, install packages, repair a rebuilt package, use
  `amerge`, and run tracked inference scenarios.
- [Current State](maintainers/current-state.md) records what has passed on the
  reference host, what is installed, and which findings are blocked or
  exploratory.

## If You Want To Understand What This Repo Changes

- [Patch Inventory](patches.md) summarizes notable original source patches and
  where to inspect the complete patch list.
- [Reference-Package Policy](policies/reference-packages.md) explains how Arch,
  CachyOS, AUR, upstream projects, and recipe inputs are used as baselines.
- [TheRock Generator Architecture](architecture/therock-generator.md) explains
  how the generated ROCm split packages are rendered from TheRock output.
- [TheRock Generator Status](maintainers/therock-generator-status.md) records
  current generator coverage and known gaps.

## If You Are Maintaining Or Updating Packages

- [Recipe Inputs](maintainers/recipe-inputs.md) explains the Blackcat
  Informatics recipe source and how it feeds local package scaffolds.
- [Update Workflows](maintainers/update-workflows.md) covers package update
  paths, including the 24-hour dependency freshness sweep.
- [Dependency Freshness Sweep](maintainers/update-workflows.md#0-dependency-freshness-sweep)
  is the first gate to check before unrelated backlog work when it is due.
- [ROCm Inference Reference](maintainers/rocm-inference-reference.md) collects
  upstream ROCm, vLLM, FlashAttention, AITER, MIGraphX, quantization, and
  profiling references that may affect future package or scenario work.
- [vLLM Recipe Coverage](maintainers/vllm-recipe-coverage.md) tracks which
  official vLLM recipe surfaces are validated, planned, advisory, or blocked.

## If You Are Picking Up Work

- [Backlog](backlog.md) is the active worklist. It favors current follow-up
  work over historical run logs.
- [Current State](maintainers/current-state.md) is the first place to check
  before claiming a package or scenario is installed, validated, blocked, or
  stale.
- [FlashAttention CK paged-KV boundary](maintainers/flashattention-ck-paged-kv.md)
  records the latest tabled vLLM CK consumer lane and the gates required before
  reopening it.
- [Rebuild Revalidation Ledger](maintainers/rebuild-revalidation.md) preserves
  the closed post-rebuild validation boundary for older findings.

## If You Are Writing Or Cleaning Up Docs

- [Documentation and Session Artifact Policy](policies/documentation-and-session-artifacts.md)
  explains what belongs in tracked docs, package-local docs, ignored worklogs,
  and session-only notes.

## Package-Local Docs

Each hand-maintained package has its own README and `recipe.json` under
`packages/<name>/`. Use those files for package-specific version, baseline,
divergence, patch, and update notes. The top-level package overview is
[packages/README.md](../packages/README.md).
