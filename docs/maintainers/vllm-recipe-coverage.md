# vLLM Recipe Coverage

Status as of 2026-04-20.

This worklist tracks how official vLLM Gemma and Qwen recipe surfaces map onto
the local Arch/TheRock `gfx1151` validation stack. These recipes are advisory
inputs, not executable truth for this host. Older ROCm reports, MI-series
guidance, large-node deployment shapes, and interactive recipe selectors can
suggest flags or feature probes, but a local scenario run must validate any
accepted instruction or explanation.

Current recipe references:

- <https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html>
- <https://recipes.vllm.ai/Google/gemma-4-31B-it?hardware=mi355x&advanced=max_batched_8k%2Cmax_num_seqs_256>
- <https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3.5.html>
- <https://recipes.vllm.ai/Qwen/Qwen3.6-35B-A3B?hardware=mi355x&features=tool_calling%2Creasoning%2Cspec_decoding&advanced=max_batched_8k%2Cmax_num_seqs_256>

Recipe coverage uses these states:

- `validated`: a local scenario has run after the self-hosted rebuild and is
  recorded in `docs/maintainers/rebuild-revalidation.md` or
  `docs/maintainers/current-state.md`.
- `tracked`: an executable scenario or helper exists, but this exact recipe
  surface still needs a reference-host result before promotion.
- `planned`: the surface belongs in the work plan, but the runnable local
  adapter, scenario, model binding, fixture, or assertion is not complete.
- `advisory-only`: the upstream shape is an install/deployment recipe or a
  model/hardware lane outside the intended local validation path. Keep it as
  documentation unless a local experiment is deliberately created. Long
  context, multimodal inputs, and missing helpers are not by themselves reasons
  to keep a surface advisory-only.

When an interactive recipe URL includes selectors such as
`advanced=max_batched_8k,max_num_seqs_256`, treat those as candidate flags
(`--max-num-batched-tokens 8192` and `--max-num-seqs 256`) even when the
rendered command keeps the base shape.

## Gemma 4

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

## Qwen3.5 And Qwen3.6

| Surface | Recipe flags or request shape | Current coverage | Planned action |
| --- | --- | --- | --- |
| Qwen3.6 BF16 reasoning | `Qwen/Qwen3.6-35B-A3B`, `--tensor-parallel-size 8` or interactive TP2, `--max-model-len 262144`, `--reasoning-parser qwen3` | `tracked` by reduced `reasoning` and `reasoning-disabled` server scenarios; unquantized eager and compiled text controls remain validated | Run the base server reasoning scenario on the reference host with a visible GPU, then run the remaining Qwen server modes one at a time. |
| Qwen3.6 FP8 AMD | `VLLM_ROCM_USE_AITER=1`, `Qwen/Qwen3.6-35B-A3B-FP8`, `--max-model-len 262144`, `--reasoning-parser qwen3`, `--trust-remote-code` | `validated` as blocked for non-AITER and forced-AITER FP8 MoE paths | Keep blocked probes; re-run only after a backend advertises gfx1151 FP8 MoE support. |
| Qwen3.6 MTP/spec decoding | `--speculative-config '{"method":"mtp","num_speculative_tokens":2}'` | `tracked` by reduced `mtp` server scenario | Run only after base server reasoning passes; keep the KV-cache capacity note with the result. |
| Qwen3.6 tool calling | interactive feature selector plus Qwen parser family; Qwen3.5 guide names `--enable-auto-tool-choice --tool-call-parser qwen3_coder` | `tracked` by reduced `tool` server scenario | Run after base reasoning passes and record whether `qwen3_coder` emits a tool call plus follow-up completion. |
| Qwen3.6 advanced selectors | interactive `max_batched_8k` and `max_num_seqs_256` | `tracked` by reduced `advanced-selectors` server scenario | Keep this exploratory so memory-fit failures do not obscure basic correctness. |
| Qwen3.5 throughput text-only | `Qwen/Qwen3.5-397B-A17B-FP8`, `-dp 8`, `--enable-expert-parallel`, `--language-model-only`, `--reasoning-parser qwen3`, `--enable-prefix-caching` | `advisory-only`; tiny Qwen3.5 smoke is validated | Keep large FP8 397B shape advisory; do not conflate it with the tiny smoke. |
| Qwen3.5 throughput multimodal | `--mm-encoder-tp-mode data`, `--mm-processor-cache-type shm`, expert parallel, prefix caching | `advisory-only` for the 397B FP8 recipe shape | Reuse the Qwen3.6 local model and generated fixtures for reduced multimodal validation where the architecture permits; keep only the 397B/DP8 recipe shape advisory. |
| Qwen3.5 latency MTP | `--speculative-config '{"method":"mtp","num_speculative_tokens":1}'`; guide notes AMD MTP-1 is under development | `advisory-only` | Keep advisory until reduced MTP behavior is validated on Qwen3.6 or a local Qwen3.5-family model. |
| Qwen3.5 tool calling | `--enable-auto-tool-choice --tool-call-parser qwen3_coder` | `advisory-only` | Share the future Qwen tool helper with Qwen3.6 if model compatibility allows. |
| Qwen3.5 benchmark client | `vllm bench serve --backend openai-chat --endpoint /v1/chat/completions --random-input-len 2048 --random-output-len 512 --num-prompts 1000 --request-rate 20` | `tracked` by reduced `benchmark-lite` server scenario, not full benchmark coverage | Use the smoke for server correctness only; keep throughput measurement as a separate benchmark task. |
| Qwen3.5 OpenAI multimodal client | `image_url` chat content, `max_tokens 2048` | `tracked` by reduced `media-embedding` server scenario | Use only local embedded media fixtures; do not depend on remote media. |
| Qwen ultra-long context | `VLLM_ALLOW_LONG_MAX_MODEL_LEN=1`, YaRN `--hf-overrides`, `--max-model-len 1010000` | `advisory-only` for full YaRN shape; reduced long-context smoke is tracked separately | Treat the full 1,010,000-token shape as an explicit stress lane after base server behavior passes. |
| Qwen reasoning disablement | `--reasoning-parser qwen3` with `--default-chat-template-kwargs '{"enable_thinking": false}'` | `tracked` by reduced `reasoning-disabled` server scenario | Run after base reasoning passes and check that the response does not include reasoning output. |
| Qwen prefix/Mamba/CUDAGraph caveat | prefix caching experimental for Mamba align; reduce `--max-cudagraph-capture-size` when capture size exceeds Mamba cache size | `planned` | Add to classification criteria for Qwen compiled failures; create a focused probe only if the failure reproduces locally. |
| Qwen media embedding tuning | `--mm-processor-kwargs '{"videos_kwargs":{"size":{"longest_edge":469762048,"shortest_edge":4096}}}'` | `tracked` by reduced `media-embedding` server scenario | Keep exploratory until a reference-host server run passes. |

The Qwen server helper now covers the reduced local scenario set with
`python -m vllm.entrypoints.openai.api_server`:

- `vllm.qwen3_6.35b-a3b.server.reasoning`
- `vllm.qwen3_6.35b-a3b.server.reasoning-disabled`
- `vllm.qwen3_6.35b-a3b.server.mtp`
- `vllm.qwen3_6.35b-a3b.server.tool`
- `vllm.qwen3_6.35b-a3b.server.benchmark-lite`
- `vllm.qwen3_6.35b-a3b.server.advanced-selectors`
- `vllm.qwen3_6.35b-a3b.server.long-context-reduced`
- `vllm.qwen3_6.35b-a3b.server.media-embedding`

All eight are exploratory until a reference-host run reaches `server_ready` and
passes its mode-specific marker. The 2026-04-20 local attempt to run
`vllm.qwen3_6.35b-a3b.server.reasoning` failed before `server_ready` because
the execution environment exposed no GPU to PyTorch while vLLM resolved the
ROCm platform. The remaining Qwen server scenarios were not run after that base
failure.
