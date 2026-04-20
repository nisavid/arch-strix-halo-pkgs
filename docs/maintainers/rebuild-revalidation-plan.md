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

## Recipe Coverage Worklist

The vLLM recipe pages are advisory input, not executable truth for this
`gfx1151` stack. The current recipe site also separates durable Markdown guides
from interactive pages; when an interactive URL includes selectors such as
`advanced=max_batched_8k,max_num_seqs_256`, treat those as candidate flags
(`--max-num-batched-tokens 8192` and `--max-num-seqs 256`) even when the
rendered command keeps the base shape.

Recipe coverage uses these states:

- `validated`: a post-rebuild local scenario has run and is recorded in
  `docs/maintainers/rebuild-revalidation.md` or
  `docs/maintainers/current-state.md`
- `tracked`: an executable scenario or helper exists, but this exact recipe
  surface still needs a post-rebuild reference-host result before promotion
- `planned`: the surface belongs in the work plan, but the runnable local
  adapter, scenario, model binding, fixture, or assertion is not complete
- `advisory-only`: the upstream shape is an install/deployment recipe or a
  model/hardware lane outside the intended local validation path; keep it as
  documentation unless a local experiment is deliberately created. Long
  context, multimodal inputs, and missing helpers are not by themselves reasons
  to keep a surface advisory-only.

Gemma 4 recipe surfaces from
<https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html> and
<https://recipes.vllm.ai/Google/gemma-4-31B-it?hardware=mi355x&advanced=max_batched_8k%2Cmax_num_seqs_256>:

| Surface | Recipe flags or request shape | Current coverage | Planned action |
| --- | --- | --- | --- |
| E4B quick start | `google/gemma-4-E4B-it`, `--max-model-len <n>` up to `131072` | `planned` | Add an optional smoke only if the E4B checkpoint is cached locally; otherwise keep advisory. |
| 31B dense serving | `--tensor-parallel-size 2`, `--max-model-len 32768`, `--gpu-memory-utilization 0.90` | `tracked` by `vllm.gemma4.31b.text.compiled`, but not server recipe coverage | Add a reduced 31B server smoke if memory allows; keep TP2 as advisory on single-host gfx1151. |
| 26B-A4B MoE serving | `--max-model-len 32768`, `--gpu-memory-utilization 0.90` | `validated` for basic text/server and MoE backend probes | No new base smoke required; keep MoE backend probes as the local tuning coverage. |
| AMD MI-series Docker shape | `vllm/vllm-openai-rocm:gemma4`, device mounts, host networking | `advisory-only` | Do not turn Docker install guidance into a repo scenario. |
| Full-feature server | `--enable-auto-tool-choice`, `--reasoning-parser gemma4`, `--tool-call-parser gemma4`, `--chat-template examples/tool_chat_template_gemma4.jinja`, `--limit-mm-per-prompt image=4,audio=1`, `--async-scheduling` | `tracked` through E2B text-only feature scenarios, not fully validated post-rebuild | Run `full-feature-text-only`, then mode-specific reasoning, tool, structured, and structured-thinking scenarios before promotion. |
| Text generation clients | OpenAI SDK and cURL chat completions, `max_tokens 512`, `temperature 0.7` | `validated` by basic text/server smokes at reduced sampling | No separate client-only lane unless a client regression appears. |
| Offline inference | `LLM(... max_model_len=8192, gpu_memory_utilization=0.90, trust_remote_code=True)` | `tracked` indirectly by text helpers | Keep server/text helper coverage unless offline-only behavior diverges. |
| Image understanding | single-image OpenAI request, `max_tokens 1024` | `validated` for E2B image smoke | Keep as representative multimodal warmup coverage; add 26B/31B only if needed. |
| Multi-image | two `image_url` inputs | `tracked` by `vllm.gemma4.e2b.server.multi-image` | Run before promoting broad multimodal recipe coverage. |
| Dynamic vision resolution | `--mm-processor-kwargs '{"max_soft_tokens": 560}'`; values `70`, `140`, `280`, `560`, `1120`; offline `hf_overrides` for `vision_soft_tokens_per_image` | `tracked` by `vllm.gemma4.e2b.server.image-dynamic` | Run the existing reduced scenario; defer full value sweep until correctness is stable. |
| Audio | E2B/E4B audio, `vllm[audio]`, `--limit-mm-per-prompt image=4,audio=1` | `tracked` by `vllm.gemma4.e2b.server.audio` | Run only after confirming local audio dependencies and fixture availability. |
| Video | E2B video request, `--limit-mm-per-prompt image=4,video=1` | `tracked` by `vllm.gemma4.e2b.server.video` | Run with a local fixture or keep pending; do not depend on remote media. |
| Thinking | `--reasoning-parser gemma4`; per-request `chat_template_kwargs.enable_thinking=true`; optional `--default-chat-template-kwargs '{"enable_thinking": true}'` | `tracked` by `reasoning`, `tool-thinking`, and `structured-thinking` scenarios | Run post-rebuild and assert response `reasoning` separately from final content. |
| Tool calling | `--enable-auto-tool-choice`, `--tool-call-parser gemma4`, Gemma 4 chat template | `tracked` by `tool`, `tool-thinking`, and `multimodal-tool` scenarios | Run text tool first; run multimodal-tool only after multimodal fixture coverage is stable. |
| Structured outputs | OpenAI `response_format={"type":"json_schema"}`; Pydantic schema shape | `tracked` by `structured` and `structured-thinking` scenarios | Run both and ensure assertions check valid JSON structure plus requested semantics. |
| Benchmarking | `--no-enable-prefix-caching`, text-only multimodal limits, `--async-scheduling`; `vllm bench serve --dataset-name random --random-input-len 8000 --random-output-len 1000 --request-rate 10000 --num-prompts 16 --ignore-eos` | `tracked` by `benchmark-lite` only | Keep `benchmark-lite` as correctness smoke; add throughput measurement only as a separate benchmark task. |
| Throughput/latency tuning | `--max-num-seqs` `256-512` for throughput, `8-16` for latency, `128` balanced; interactive `--max-num-batched-tokens 8192` and `--max-num-seqs 256` selectors | `planned` | Add bounded tuning probes after base feature lanes pass; promote larger batch settings when the run records memory-fit evidence. |
| Memory tuning | reduce `--max-model-len`; `--kv-cache-dtype fp8`; `--limit-mm-per-prompt image=2,audio=1`; `--gpu-memory-utilization 0.85-0.95` | `planned` except existing text-only limits and `0.90` controls | Add an FP8 KV-cache smoke and a bounded max-seqs/max-batched probe where the host can fit it. |

Qwen3.5/Qwen3.6 recipe surfaces from
<https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3.5.html> and
<https://recipes.vllm.ai/Qwen/Qwen3.6-35B-A3B?hardware=mi355x&features=tool_calling%2Creasoning%2Cspec_decoding&advanced=max_batched_8k%2Cmax_num_seqs_256>:

| Surface | Recipe flags or request shape | Current coverage | Planned action |
| --- | --- | --- | --- |
| Qwen3.6 BF16 reasoning | `Qwen/Qwen3.6-35B-A3B`, `--tensor-parallel-size 8` or interactive TP2, `--max-model-len 262144`, `--reasoning-parser qwen3` | `validated` for unquantized eager and compiled text controls, not server reasoning | Add a local server reasoning scenario using the cached unquantized checkpoint; start with a bounded smoke length, then add a 262K context stress lane if the base server path passes. |
| Qwen3.6 FP8 AMD | `VLLM_ROCM_USE_AITER=1`, `Qwen/Qwen3.6-35B-A3B-FP8`, `--max-model-len 262144`, `--reasoning-parser qwen3`, `--trust-remote-code` | `validated` as blocked for non-AITER and forced-AITER FP8 MoE paths | Keep blocked probes; re-run only after a backend advertises gfx1151 FP8 MoE support. |
| Qwen3.6 MTP/spec decoding | `--speculative-config '{"method":"mtp","num_speculative_tokens":2}'` | `planned` as advisory recipe surface | Add a reduced MTP server scenario after the base server reasoning scenario passes; include a KV-cache capacity note. |
| Qwen3.6 tool calling | interactive feature selector plus Qwen parser family; Qwen3.5 guide names `--enable-auto-tool-choice --tool-call-parser qwen3_coder` | `planned` | Add a Qwen server helper/tool payload before adding an executable scenario. |
| Qwen3.6 advanced selectors | interactive `max_batched_8k` and `max_num_seqs_256` | `planned` | Add memory-fit probes after base Qwen3.6 server lanes pass; keep them separate from default smokes so throughput tuning failures do not obscure basic correctness. |
| Qwen3.5 throughput text-only | `Qwen/Qwen3.5-397B-A17B-FP8`, `-dp 8`, `--enable-expert-parallel`, `--language-model-only`, `--reasoning-parser qwen3`, `--enable-prefix-caching` | `advisory-only`; tiny Qwen3.5 smoke is validated | Keep large FP8 397B shape advisory; do not conflate it with the tiny smoke. |
| Qwen3.5 throughput multimodal | `--mm-encoder-tp-mode data`, `--mm-processor-cache-type shm`, expert parallel, prefix caching | `advisory-only` for the 397B FP8 recipe shape | Reuse the Qwen3.6 local model and generated fixtures for reduced multimodal validation where the architecture permits; keep only the 397B/DP8 recipe shape advisory. |
| Qwen3.5 latency MTP | `--speculative-config '{"method":"mtp","num_speculative_tokens":1}'`; guide notes AMD MTP-1 is under development | `advisory-only` | Keep advisory until reduced MTP behavior is validated on Qwen3.6 or a local Qwen3.5-family model. |
| Qwen3.5 tool calling | `--enable-auto-tool-choice --tool-call-parser qwen3_coder` | `advisory-only` | Share the future Qwen tool helper with Qwen3.6 if model compatibility allows. |
| Qwen3.5 benchmark client | `vllm bench serve --backend openai-chat --endpoint /v1/chat/completions --random-input-len 2048 --random-output-len 512 --num-prompts 1000 --request-rate 20` | `advisory-only` | Add benchmark-lite only after a Qwen server helper exists. |
| Qwen3.5 OpenAI multimodal client | `image_url` chat content, `max_tokens 2048` | `advisory-only` | Use local image fixtures for any future executable test. |
| Qwen ultra-long context | `VLLM_ALLOW_LONG_MAX_MODEL_LEN=1`, YaRN `--hf-overrides`, `--max-model-len 1010000` | `planned` | Treat as an explicit stress lane, separate from smoke validation, after base long-context behavior is understood. |
| Qwen reasoning disablement | `--reasoning-parser qwen3` with `--default-chat-template-kwargs '{"enable_thinking": false}'` | `planned` | Add as a reduced server toggle check after the base reasoning scenario exists. |
| Qwen prefix/Mamba/CUDAGraph caveat | prefix caching experimental for Mamba align; reduce `--max-cudagraph-capture-size` when capture size exceeds Mamba cache size | `planned` | Add to classification criteria for Qwen compiled failures; create a focused probe only if the failure reproduces locally. |
| Qwen media embedding tuning | `--mm-processor-kwargs '{"videos_kwargs":{"size":{"longest_edge":469762048,"shortest_edge":4096}}}'` | `planned` | Add after reduced Qwen multimodal coverage exists, using local generated media fixtures. |

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
- the tracked control arguments, including `--max-num-batched-tokens 32` and
  `--gpu-memory-utilization 0.9`
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
