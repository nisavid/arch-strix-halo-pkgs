# FlashAttention CK Paged-KV Boundary

This maintainer note preserves the 2026-04-23/2026-04-24 attempt to route
vLLM Qwen3.5 through the packaged ROCm FlashAttention CK backend on Strix Halo
`gfx1151`.

Document type: reference plus explanation. Target audience: maintainers who
need to decide whether to reopen the CK paged-KV lane. Goal: keep the tested
facts, source clues, likely failure model, and next validation gates available
without relying on chat history.

## Status

The CK Qwen3.5 engine path is tabled. Keep it as a possible future upstream
kernel or kernel-specialization task, not as an active local adapter task.

Do not promote `vllm.qwen3_5.0_8b.text.flash-attn-ck` unless one of these
gates passes on the reference host:

- CK accepts the vLLM Qwen paged-KV shape with 64-token kernel pages and
  matches a reference implementation.
- A different validated backend handles the same Qwen route.
- Upstream FlashAttention or CK lands a paged-KV fix that passes the local
  scenario matrix.

## Local Evidence

The package-level CK surface works for bounded direct tests. With
`python-flash-attn-rocm-gfx1151 2.8.4-10`, the tracked installed scenarios
`flash-attn.ck.backend-import`, `flash-attn.ck.qkvpacked-tiny`,
`flash-attn.ck.varlen-tiny`, `flash-attn.ck.varlen-tiny-d256`, and
`flash-attn.ck.varlen-paged-kv` passed at run root
`docs/worklog/inference-runs/20260423T223607`.

The vLLM Qwen CK consumer probe is still an expected blocked kernel probe. With
`python-vllm-rocm-gfx1151 0.19.1-6` and
`python-flash-attn-rocm-gfx1151 2.8.4-10`, the scenario
`vllm.qwen3_5.0_8b.text.flash-attn-ck` confirms that vLLM selects CK
(`flash_attn_2_cuda` with `FLASH_ATTENTION_TRITON_AMD_ENABLE=FALSE`), reports
FlashAttention version 2, accepts the local vLLM-shaped varlen wrapper
keywords, and reaches `llm_init_ok`. The normal Qwen3.5 hybrid path then
presents `k_shape=(69080, 64, 2, 256)`, and CK rejects the page shape with
`Paged KV cache block size must be divisible by 128`. The expected blocked
scenario passed at run root `docs/worklog/inference-runs/20260423T224553`.

Diagnostic overrides that forced a 128-divisible effective page moved past the
Python shape check and faulted the GPU inside CK. Observed diagnostic shapes
included `k_shape=(6906, 640, 2, 256)` and
`k_shape=(11513, 384, 2, 256)`. Treat this as evidence that removing the
wrapper guard is not safe.

## Source Disposition

| Source | Source type | Retrieved | Validation status | Ingestion destination | Next gate | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| <https://github.com/Dao-AILab/flash-attention/issues/1579> | upstream GitHub issue | 2026-04-24 | `advisory-only` | this file; `docs/backlog.md`; `docs/maintainers/current-state.md` | direct CK 64-page reproducer | The issue asks whether ROCm CK can support smaller paged-KV block sizes such as 8, 16, 32, and 64 for vLLM V1. It has no upstream resolution yet. |
| <https://github.com/Dao-AILab/flash-attention/pull/1198> | upstream GitHub PR | 2026-04-24 | `advisory-only` | this file | source trace before any CK patch | Added CK page-kvcache support. The same 128-divisibility guard appears in this lane. |
| <https://github.com/Dao-AILab/flash-attention/pull/1431> | upstream GitHub PR | 2026-04-24 | `advisory-only` | this file | source trace before any CK patch | Added ROCm CK variable-length paged attention. Tests covered `None`, `256`, and `512`, not `64`. |
| <https://github.com/Dao-AILab/flash-attention/issues/1627> | upstream GitHub issue | 2026-04-24 | `advisory-only` | this file | compare against any future FA3 ROCm path | Upstream maintainer states that FlashAttention-3 has no page-size restriction. This argues against a model-level impossibility. |
| <https://github.com/Dao-AILab/flash-attention/issues/1974> | upstream GitHub issue | 2026-04-24 | `advisory-only` | this file; `packages/python-vllm-rocm-gfx1151/README.md` | NaN-tail repro before forcing page size 128 | Explains the FlashAttention NaN hazard when kernels read padded or logically unused V values. |
| <https://github.com/vllm-project/vllm/issues/27264> | upstream GitHub issue | 2026-04-24 | `advisory-only` | this file; `packages/python-vllm-rocm-gfx1151/README.md` | keep vLLM 64-page choice unless CK proves a safe alternative | Records the hybrid Mamba/attention NaN investigation that led vLLM to avoid FlashAttention block sizes at or above 128 in this class of model. |
| <https://github.com/vllm-project/vllm/pull/27753> | upstream GitHub PR | 2026-04-24 | `validated` | this file; `packages/python-vllm-rocm-gfx1151/README.md` | keep local patch carry aligned with upstream block-size selection | This is the vLLM change that passes kernel block size through metadata builders and restricts FlashAttention to `[16, 32, 64]` for the affected hybrid cache case. The installed package follows that behavior. |
| <https://github.com/vllm-project/vllm/pull/31380> | upstream GitHub PR | 2026-04-24 | `advisory-only` | this file | use as a design clue, not as CK proof | Shows that nonstandard ROCm attention block support can require backend address-calculation work, not just wrapper relaxation. |
| <https://docs.vllm.ai/en/latest/design/hybrid_kv_cache_manager.html> | upstream docs | 2026-04-24 | `advisory-only` | this file; Qwen scenario notes | recheck when vLLM hybrid KV manager changes | Explains why hybrid models reconcile different attention and Mamba state sizes through a common page-size story. |
| <https://docs.vllm.ai/en/latest/design/paged_attention.html> | upstream docs | 2026-04-24 | `advisory-only` | this file | background only | PagedAttention itself does not imply a 128-token page requirement. |
| <https://huggingface.co/Qwen/Qwen3.5-0.8B/blob/main/config.json> | model config | 2026-04-24 | `validated` by local scenario assertions | this file; `inference/scenarios/vllm-qwen.toml` | rerun after model config or vLLM loader changes | The targeted small model is hybrid and uses `head_dim=256`, `num_attention_heads=8`, and `num_key_value_heads=2`. |
| <https://huggingface.co/papers/2205.14135> | paper index | 2026-04-24 | `advisory-only` | this file | background only | FlashAttention is IO-aware tiled attention; page-size constraints come from concrete kernels, not the mathematical attention operation. |
| <https://arxiv.org/abs/2309.06180> | paper | 2026-04-24 | `advisory-only` | this file | background only | PagedAttention motivates block-based KV allocation and sharing, but it does not require CK's 128-token multiple. |

## Interpretation

The discovered evidence does not show that a 64-token paged-KV dimension is
impossible on Strix Halo or in FlashAttention generally. It shows that the
current ROCm CK FlashAttention-2 paged-KV implementation was built and tested
behind a 128-divisibility contract.

The likely technical factor is CK tile/page geometry. The CK paged-KV path
maps K/V tile windows through page-block navigation. If the active K-sequence
tile is effectively 128 tokens, a 64-token page makes ordinary K/V tiles cross
physical page boundaries every time. Supporting that safely likely needs a
64-page kernel specialization or stronger cross-page gather and masking logic.
The wrapper guard prevents launching kernels outside the validated geometry.

This is an implementation constraint, not a proven hardware rule. CUDA FA2 has
had a stricter documented page-size multiple, CK lowered the visible guard to
128, and FA3 upstream reports arbitrary page-size support. Those facts point
to kernel implementation and validation coverage as the active boundary.

## Workarounds Considered

Forcing vLLM toward a 128-divisible page is not a safe workaround. It conflicts
with vLLM's upstream NaN mitigation for hybrid cache layouts and, on this host,
diagnostic forced-page runs progressed to GPU memory-access faults inside CK.

Removing the Python `page_block_size % 128` guard is not a safe workaround.
The guard is close to the symptom, not the demonstrated root cause. A direct
64-page correctness test must pass before the guard can be relaxed.

The local vLLM adapter is not the remaining blocker. The current package
accepts vLLM's paged-KV varlen keyword surface, reports FA2 on ROCm, copies
results into explicit `out` tensors, and rejects unsupported scheduler,
descale, split-control, and `return_softmax_lse` cases with clear errors.

## Existing Tests To Keep

Keep these tracked scenarios as the active regression surface:

```sh
python tools/run_inference_scenarios.py \
  --scenario flash-attn.ck.backend-import \
  --scenario flash-attn.ck.qkvpacked-tiny \
  --scenario flash-attn.ck.varlen-tiny \
  --scenario flash-attn.ck.varlen-tiny-d256 \
  --scenario flash-attn.ck.varlen-paged-kv
```

```sh
python tools/run_inference_scenarios.py \
  --scenario vllm.qwen3_5.0_8b.text.flash-attn-ck
```

The first command proves the direct CK package surface. The second command
should remain an expected blocked probe until the CK paged-KV kernel boundary
changes.

## If This Is Reopened

Start with a direct CK reproducer before changing vLLM behavior:

1. Generate Qwen-like paged-KV tensors with `head_dim=256`, two KV heads, and
   page sizes `64` and `128`.
2. Compare CK output against a torch reference for causal varlen attention
   across ragged sequence lengths and block-table layouts.
3. Poison logically unused cache regions with `NaN` and `Inf` values, then
   confirm the output remains finite when those values are outside the logical
   sequence.
4. Exercise page-boundary crossings directly, especially cases where a K/V
   tile starts near the end of one 64-token page and continues into the next.
5. Only after direct CK correctness passes, rerun
   `vllm.qwen3_5.0_8b.text.flash-attn-ck` without diagnostic block-size
   overrides.

Treat a successful Python launch as insufficient. The gate is reference-match
correctness plus a clean vLLM scenario on the reference host.

## Related Repo Files

- `inference/scenarios/flash-attn.toml`: direct CK and Triton AMD FlashAttention
  scenarios.
- `inference/scenarios/vllm-qwen.toml`: Qwen3.5 CK expected blocked probe.
- `packages/python-flash-attn-rocm-gfx1151/README.md`: FlashAttention package
  evidence and CK boundaries.
- `packages/python-vllm-rocm-gfx1151/README.md`: vLLM adapter and backend-gate
  boundaries.
- `docs/maintainers/current-state.md`: latest installed host evidence.
- `docs/backlog.md`: deferred follow-up position.
