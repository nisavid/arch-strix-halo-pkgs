# Rebuild Revalidation Execution Plan

Status as of 2026-04-20.

This plan turns `docs/maintainers/rebuild-revalidation.md` into an execution
workflow. It assumes the self-hosted native rebuild is complete and processes
revalidation in the package root order reported by:

```bash
tools/amerge run --dry-run --all --json
```

## Scope

In scope:

- locally originated patch carry in package sources and generated PKGBUILD
  inline edits
- expected-failure tests and blocked inference probes that may have depended
  on stale build-time or runtime dependencies
- backlog findings whose failure mode could plausibly change after the
  self-hosted rebuild
- runtime conclusions recorded before the 2026-04-20 revalidation boundary

Out of scope:

- patches sourced directly from upstream or from Blackcat Informatics recipe
  inputs, unless this repo also records a separate dependency-sensitive runtime
  finding around that behavior
- package policy, metadata, and presentation decisions that cannot be explained
  by stale self-hosted dependencies
- online reports or documentation unless local validation reproduces the
  behavior on this TheRock/AITER stack

## Build Order

Process rows and follow-up checks in this root order:

1. `therock-gfx1151`
2. `aocl-utils-gfx1151`
3. `lemonade-server`
4. `llama.cpp-hip-gfx1151`
5. `llama.cpp-vulkan-gfx1151`
6. `python-gfx1151`
7. `aocl-libm-gfx1151`
8. `lemonade-app`
9. `python-asyncpg-gfx1151`
10. `python-cryptography-gfx1151`
11. `python-numpy-gfx1151`
12. `python-openai-harmony-gfx1151`
13. `python-orjson-gfx1151`
14. `python-sentencepiece-gfx1151`
15. `python-triton-gfx1151`
16. `python-zstandard-gfx1151`
17. `lemonade`
18. `python-aotriton-gfx1151`
19. `python-mistral-common-gfx1151`
20. `python-transformers-gfx1151`
21. `python-pytorch-opt-rocm-gfx1151`
22. `python-amd-aiter-gfx1151`
23. `python-torchao-rocm-gfx1151`
24. `python-torchvision-rocm-gfx1151`
25. `python-vllm-rocm-gfx1151`

For roots without pending ledger rows, confirm there is no package-local
`README.md`, `recipe.json`, patch file, expected-failure test, or backlog item
that creates a dependency-sensitive revalidation obligation. Do not invent
runtime work for roots that have only package-policy changes.

## Source Inventory

Before executing a row, collect the local source facts:

- package metadata: `packages/<name>/recipe.json`,
  `packages/<name>/README.md`, and `policies/recipe-packages.toml`
- patch application: source patch files and generated PKGBUILD patch or
  inline-edit blocks
- existing executable specs: `tests/`, `inference/scenarios/`, package-local
  tests, and focused smoke tools
- current state and backlog references: `docs/maintainers/current-state.md`,
  `docs/backlog.md`, and `docs/patches.md`
- history and session context when motivation is missing: git history, tracked
  worklog material, and available Codex transcripts

## Advisory References

Use Hugging Face model cards, vLLM model usage recipes, vLLM issues and PRs,
vLLM commit history, release notes, and current vLLM docs as hints for specific
features, expected backend markers, and failure signatures. Especially useful
vLLM references include:

- <https://docs.vllm.ai/en/latest/getting_started/installation/gpu/>
- <https://docs.vllm.ai/en/latest/features/>

AMD ROCm documentation can also provide useful conceptual guidance, but most
AI optimization material is written for MI-series/Instinct GPUs or preview
Ryzen enablement rather than this Arch/TheRock `gfx1151` stack. Treat these as
candidate checklists and tuning hypotheses, not as direct instructions:

- <https://rocm.docs.amd.com/en/7.12.0-preview/compatibility/compatibility-matrix.html?fam=ryzen&gpu=max-395&os=ubuntu&i=docker>
- <https://rocm.docs.amd.com/en/7.12.0-preview/rocm-for-ai/vllm.html?fam=ryzen&gpu=max-395&i=pip&os=linux&os-version=24.04>
- <https://rocm.docs.amd.com/en/latest/how-to/rocm-for-ai/inference-optimization/workload.html>
- <https://rocm.docs.amd.com/en/latest/how-to/rocm-for-ai/inference-optimization/vllm-optimization.html>

FlashAttention's AMD ROCm support notes are relevant when considering an AITER
FlashAttention experiment:

- <https://github.com/Dao-AILab/flash-attention#amd-rocm-support>

Treat external material as advisory. Older ROCm reports can suggest search
terms or repro ideas, but they do not become accepted explanations or
instructions until a local rebuilt-stack run validates them.

## Decision Tree

For each pending row:

1. Identify the patch, finding, scenario, or expected failure named by the row.
2. Decide whether the row is local-origin scope, upstream/recipe scope with a
   repo-local runtime finding, or explicit skip scope.
3. If an executable spec already exists, use it as the first repro. If it does
   not exist, reconstruct the motivation from local docs, history, transcripts,
   and patch context, then add the smallest retained guard that can cover the
   accepted behavior.
4. Run the package-local guard or inference scenario against the rebuilt
   installed stack. Capture package versions, model binding, backend markers,
   exit code, and the relevant output or failure signature.
5. Classify the result using the outcome rules below.
6. Update the ledger status and the durable target doc in the same change.

## Outcomes

Use deterministic outcomes when the evidence is unambiguous:

- `accepted`: the post-rebuild run matches the expected pass or failure
  signature, the relevant guard is tracked, and the accepted rationale is
  written in the target doc.
- `retired`: the provisional patch or expected failure is no longer needed,
  or the behavior is correct without it. Remove or disable the patch or
  expected-failure assertion in a focused follow-up.
- `pending`: required evidence is missing, the run is blocked by an
  environmental prerequisite, or the observed behavior is different enough that
  the row needs narrower investigation.

Use context-sensitive judgment when:

- the same failure class appears with a different spelling or stack location
- a patch group covers one failure condition and patch-off testing would be
  impractical or too expensive
- upstream behavior changed and the local finding may need to be split instead
  of accepted or retired wholesale
- the available model, cache path, or hardware mode differs from the original
  pre-boundary evidence

In those cases, keep the row `pending` unless the durable doc explains why the
evidence is equivalent.

## Acceptance Criteria

Accepted retained patches require:

- a local post-rebuild run or package-local test recorded in the durable target
  doc
- an executable guard that fails without the patch and passes with it, or a
  written explanation of why exact patch-off testing is impractical and what
  equivalent guard covers the failure condition
- no reliance on stale host packages, ambient shell state, or undocumented
  model bindings
- the ledger row status updated from `pending`

Accepted expected-failure tests and blocked probes require:

- the same failure class reproduced after the rebuild
- an assertion that matches the failure class without overfitting incidental log
  text
- a clear promotion target that says why the failure remains expected

Retired items require:

- evidence that the rebuilt stack behaves correctly without the provisional
  patch or expected-failure condition
- a follow-up change that removes the stale patch, skip, or expected-failure
  assertion
- docs updated to avoid preserving the retired explanation as current guidance

Blocked items require:

- the command attempted, the missing prerequisite or environmental blocker, and
  the next concrete unblock step
- no promotion into accepted docs

## Qwen3.6 Control Rule

Run `vllm.qwen3_6.35b-a3b.text.unquantized-moe-no-aiter-control` before
classifying either Qwen3.6 FP8 probe as FP8-specific. The control must capture:

- model binding for `Qwen/Qwen3.6-35B-A3B`
- `config_quantization_config_present false`
- `config_model_type qwen3_5_moe`
- `text_config_model_type qwen3_5_moe_text`
- hidden-layer, expert, expert-per-token, and layer-type markers
- `Using TRITON backend for Unquantized MoE`
- `llm_init_ok`, `generation_ok`, and `basic_ok`

Only after this control passes may the FP8 blocked probes be classified as
FP8-specific. FP8 probes must assert `config_quantization_config_present true`
so a missing quantization config cannot masquerade as an FP8 backend result.

## Delegation

Delegate simple action execution and output extraction to `gpt-5.4-mini-xhigh`:
single scenario runs, exit-code extraction, backend marker collection, package
version collection, and concise log excerpts.

Keep investigation, classification, debugging, coding, testing, judgment, and
durable writing on `gpt-5.4-high`: deciding reproduced versus retired, adding
guards, narrowing failure classes, and updating maintainer docs.

Every delegated result must be checked against local files, command output, or
scenario logs before changing tracked docs.
