---
name: ingesting-rocm-inference-references
description: Use when ROCm, vLLM, AITER, FlashAttention, MIGraphX, quantization, profiling, or inference-optimization references need to become package notes, backlog items, scenarios, or troubleshooting docs in this repo.
---

# Ingesting ROCm Inference References

## Overview

ROCm references are inputs, not evidence. Preserve exact sources, classify each
claim, and promote nothing from advisory to validated until a local gfx1151 run
proves it.

## Required Sinks

Open `docs/maintainers/rocm-inference-reference.md` first. Then choose the
smallest durable sink:

| Item | Sink |
| --- | --- |
| Source index, diagrams, concepts | `docs/maintainers/rocm-inference-reference.md` |
| Source, tool, or experiment | `docs/backlog.md` |
| Existing verified blocker or live state | `docs/maintainers/current-state.md` |
| vLLM recipe or flag surface | `docs/maintainers/vllm-recipe-coverage.md` |
| Runnable local coverage | `inference/scenarios/` plus catalog tests |
| Package maintenance policy | package README, `recipe.json`, or policy TOML |

## Source Disposition

For every source, record:

- exact URL, branch/tag/version, retrieval date, and source type
- extracted package candidates, scenario candidates, troubleshooting notes,
  and future reference value
- status: `validated`, `planned`, `advisory-only`, or
  `requires-host-validation`
- affected existing failures, or `no affected tracked failure found`

If the active environment supports explicit parallel delegation and the user
has requested or allowed it, split broad source sets by source group. Otherwise
process sources serially. Every pass returns the same source disposition
fields. The main agent reconciles every item into a sink, defers it with a
reason, or rejects it as not useful here.

## Guardrails

- Treat MI300X, MI350X, CDNA, and Instinct guidance as advisory-only for Strix
  Halo/gfx1151 until a host run changes that status.
- Do not copy long upstream prose or images. Use short summaries, exact URLs,
  and Mermaid diagrams when a diagram is useful.
- Do not create a package entry until source audit and package policy justify
  it. Backlog candidates are not validated packages.
- Do not mark vLLM, quantization, or FlashAttention failures unblocked without
  a local scenario result and current-state update.
- Delete `.agents/session/` extraction notes after durable docs are updated.

## Verification

Run focused policy and catalog tests, then `git diff --check`. If a new
scenario is added, run catalog tests before any live host smoke.
