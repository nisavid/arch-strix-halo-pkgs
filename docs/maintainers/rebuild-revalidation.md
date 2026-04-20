# Rebuild Revalidation Ledger

Status as of 2026-04-20.

This ledger is the quarantine bucket for runtime findings and patch rationale
that may have depended on stale build-time or runtime dependencies from the
first full stack build. The confidence boundary is 2026-04-20, when the repo
started treating self-hosted rebuild validation as the source of truth for
accepted runtime behavior.

The full rebuild completion date is recorded in `docs/maintainers/current-state.md`
when the rebuilt stack is installed and tested.

## Status Values

- `pending`: carried or documented provisionally, but not yet accepted after
  the self-hosted rebuild.
- `reproduced`: the post-rebuild run matched the expected pass or failure
  signature, and the item is ready to promote into accepted docs.
- `accepted`: promoted into the accepted patch inventory or current-state
  narrative after post-rebuild evidence.
- `retired`: no longer reproduces after the self-hosted rebuild; remove or
  disable any associated patch in a focused follow-up.

## Promotion Rules

- Build/package-shape patches can move to `accepted` after the affected package
  rebuilds cleanly against the self-hosted stack and package-local tests pass.
- Runtime/inference patches need an installed-host run through
  `tools/run_inference_scenarios.py`, or an equivalent documented smoke, after
  the rebuilt dependency stack is installed.
- Blocked probes remain valid only when the post-rebuild run reproduces the
  same failure class and the assertion is tracked as an expected outcome.
- If the post-rebuild stack behaves correctly without a provisional patch,
  mark the item `retired`, remove the patch in a separate change, and update
  the accepted docs.

## Pending Revalidation

| Status | Area | Finding or patch | Pre-boundary evidence | Required post-rebuild evidence | Promotion target |
| --- | --- | --- | --- | --- | --- |
| pending | vLLM/Triton | `python-vllm-rocm-gfx1151/0003-rocm-gate-vendored-triton-kernels-on-runtime-support.patch` | Vendored `triton_kernels` imports failed when the installed Triton runtime lacked CUDA-only APIs. | Rebuild and install Triton plus vLLM, then run version/help smoke and at least one promoted vLLM inference scenario. | `docs/patches.md` vLLM |
| pending | vLLM/ROCm platform | `python-vllm-rocm-gfx1151/0004-rocm-fallback-and-optional-sagemaker-standards.patch` | AMDSMI fallback and optional SageMaker imports affected generic CLI/API startup. | Rebuild and install vLLM, then run `vllm --help`, `vllm --version`, and promoted Gemma/Qwen scenarios without import-time failures. | `docs/patches.md` vLLM |
| pending | Gemma 4 attention | `python-vllm-rocm-gfx1151/0005-rocm-reduce-triton-unified-attention-prefill-tile-for-large-heads.patch` | Large-head ROCm Triton unified-attention prefill could exceed the gfx1151 LDS limit. | Run the promoted Gemma 4 text/server lanes and confirm the large-head prefill path no longer faults; retire if the rebuilt Triton/vLLM lane no longer needs the tile reduction. | `docs/patches.md` vLLM |
| pending | vLLM build hygiene | `python-vllm-rocm-gfx1151/0006-setup.py-forward-host-and-hip-flags-into-cmake.patch` | HIP extension builds missed inherited prefix-map and tuning flags. | Rebuild vLLM and inspect shipped extensions/debug metadata for sanitized source paths. | `docs/patches.md` vLLM |
| pending | Gemma 4 AITER attention | `python-vllm-rocm-gfx1151/0007-rocm-enable-gfx1x-aiter-and-prefer-it-for-gemma4.patch` | Gemma 4 needed gfx1x AITER discovery and `ROCM_AITER_UNIFIED_ATTN` selection to avoid the earlier Triton unified-attention decode failure. | Run promoted Gemma 4 text/server scenarios and confirm the backend split in scenario logs. | `docs/patches.md` vLLM |
| pending | TorchAO startup | `python-vllm-rocm-gfx1151/0008-torchao-startup-stays-lazy.patch` | Generic vLLM startup surfaced warning noise from a broken external TorchAO package. | Run generic vLLM CLI smokes and TorchAO scenarios after the local TorchAO lane is rebuilt and installed. | `docs/patches.md` vLLM |
| pending | vLLM startup imports | `python-vllm-rocm-gfx1151/0009-cli-startup-stays-runtime-light.patch` | Plain CLI/help paths imported benchmark, OpenAI, Transformers, and runtime command trees eagerly. | Run `vllm --help`, `vllm --version`, and promoted scenarios on the rebuilt stack; confirm no unrelated optional runtime import failures. | `docs/patches.md` vLLM |
| pending | Qwen3.5 hybrid/GDN | `python-vllm-rocm-gfx1151/0010-rocm-support-qwen35-hybrid-gdn.patch` | Qwen3.5-family hybrid/GDN lanes needed ROCm-safe autotune, exponent, warmup, block-size, and attention-backend handling. | Run `vllm.qwen3_5.0_8b.text.basic` after the rebuilt stack is installed. | `docs/patches.md` vLLM |
| pending | Qwen sampler | `python-vllm-rocm-gfx1151/0011-rocm-avoid-triton-topk-topp-sampler.patch` | The Triton top-k/top-p filter faulted on the Qwen3.5-family large-vocabulary logits shape. | Run the Qwen sampler scenario and, if needed, a focused sampler repro against the rebuilt Triton/vLLM stack. | `docs/patches.md` vLLM |
| pending | AITER headers | `python-amd-aiter-gfx1151/0001-gfx1151-rdna35-header-compat.patch` and `0006-rdna35-hip-reduce-wave32-dpp-compat.patch` | gfx1151 builds needed RDNA 3.5 header compatibility for packed ops and wave32/DPP reduction helpers. | Rebuild AITER and run promoted Gemma/Qwen scenarios that import or JIT AITER modules. | `docs/patches.md` AITER |
| pending | AITER installed JIT | `python-amd-aiter-gfx1151/0002-jit-runtime-finds-hipcc-and-user-jit-modules.patch` | Installed systems needed deterministic `hipcc` resolution and user-cache JIT imports. | Run a scenario that imports AITER JIT modules after package install without ambient shell PATH assumptions. | `docs/patches.md` AITER |
| pending | AITER MoE compatibility | `python-amd-aiter-gfx1151/0003-fused-moe-unknown-gfx-falls-back-to-2stage.patch`, `0004-moe-tuner-skips-missing-1stage-asm-metadata.patch`, and `0005-ck-moe-normalizes-zero-splitk-and-forwards-stage2.patch` | gfx1x AITER MoE experiments needed unknown-gfx fallback, missing metadata tolerance, and CK splitk normalization. | Re-run the forced AITER MoE probes only when that lane is intentionally under investigation; keep default Gemma 4 on Triton MoE unless fresh evidence changes the lane. | `docs/patches.md` AITER |
| pending | Qwen3.6 blocked probe | `vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-no-aiter-blocked` | The non-AITER FP8 MoE path reported no backend support for gfx1151. | Run the blocked probe after the rebuilt stack is installed and confirm the same backend-selection failure class. | `docs/maintainers/current-state.md` |
| pending | Qwen3.6 forced AITER probe | `vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-aiter-blocked` | The forced AITER path reached `module_quant` and failed on `mfma_adaptor`. | Run the blocked probe after the rebuilt stack is installed and confirm the same or updated AITER feature-gap signature. | `docs/maintainers/current-state.md` |
| pending | Gemma 4 scenario matrix | Promoted and exploratory Gemma 4 vLLM scenarios | Several pass/fail conclusions were drawn before the full self-hosted rebuild completed. | Re-run promoted non-exploratory Gemma 4 scenarios first, then exploratory compiled, MoE, TorchAO, and multimodal lanes by explicit selector. | `docs/maintainers/current-state.md` |
| pending | TorchAO runtime lane | Local `python-torchao-rocm-gfx1151` plus vLLM TorchAO probes | Generic startup was separated from actual TorchAO quantization behavior, and some real-model probes remained exploratory. | Rebuild and install TorchAO and vLLM, then run tiny and selected real-model TorchAO scenarios. | `docs/maintainers/current-state.md` |

## Accepted Items Not Quarantined

The following categories are not blocked by this ledger unless a post-rebuild
run produces new contradictory evidence:

- package policy and metadata decisions that do not depend on runtime behavior
- Python version compatibility patches validated by package build/test results
- Lemonade system-managed backend policy patches
- baseline package selection and recipe provenance documentation
