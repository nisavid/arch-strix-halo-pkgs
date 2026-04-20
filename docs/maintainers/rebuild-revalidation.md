# Rebuild Revalidation Ledger

Status as of 2026-04-20.

This ledger is the quarantine bucket for locally originated patch carry,
expected-failure tests, backlog findings, and runtime conclusions that may
have depended on stale build-time or runtime dependencies from the first full
stack build. The confidence boundary is 2026-04-20, when the repo started
treating self-hosted rebuild validation as the source of truth for accepted
runtime behavior.

Do not use `docs/patches.md` as the exhaustive patch source. It is a curated
summary. For patch revalidation, start from the actual applied patch metadata:
`policies/recipe-packages.toml`, `packages/*/recipe.json`, and the generated
`packages/*/PKGBUILD` patch application blocks.

## Status Values

- `pending`: carried or documented provisionally, but not yet accepted after
  the self-hosted rebuild.
- `reproduced`: the post-rebuild run matched the expected pass or failure
  signature, and the item is ready to promote into accepted docs.
- `accepted`: promoted into accepted docs after post-rebuild evidence.
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
- Patches sourced directly from upstream, Blackcat Informatics' recipe work, or
  recipe dynamic-patching scripts are not revalidated as local-origin patch
  carry. Revalidate the local runtime finding only when the repo also records a
  dependency-sensitive expected failure or backlog item around that behavior.
- If the post-rebuild stack behaves correctly without a provisional patch,
  mark the item `retired`, remove the patch in a separate change, and update
  the accepted docs.

## Pending Revalidation

| Status | Area | Finding or patch | Pre-boundary evidence | Required post-rebuild evidence | Promotion target |
| --- | --- | --- | --- | --- | --- |
| pending | SentencePiece closure | `python-sentencepiece-gfx1151/0001-bundle-sentencepiece-by-default.patch` | The earlier Gemma 4 tokenizer failure was traced to an installed extension still linked against stale host `sentencepiece`, `protobuf`, and `abseil` libraries. | Rebuild and install `python-sentencepiece-gfx1151`, then verify the installed extension is self-contained at the ELF level and rerun at least one Gemma 4 tokenizer/vLLM smoke that imports it through the rebuilt stack. | `docs/patches.md` or `packages/python-sentencepiece-gfx1151/README.md` |
| pending | vLLM CLI version path | `python-vllm-rocm-gfx1151/0002-cli-version-avoids-eager-runtime-imports.patch` | `vllm --version` needed to stay off optional OpenAI/Triton runtime imports. | Rebuild and install vLLM plus its local dependency closure, then run `vllm --version` without relying on absent or stale host extras. | `docs/patches.md` vLLM |
| pending | vLLM/Triton | `python-vllm-rocm-gfx1151/0003-rocm-gate-vendored-triton-kernels-on-runtime-support.patch` | Vendored `triton_kernels` imports failed when the installed Triton runtime lacked CUDA-only APIs. | Rebuild and install Triton plus vLLM, then run version/help smoke and at least one promoted vLLM inference scenario. | `docs/patches.md` vLLM |
| pending | vLLM/ROCm platform | `python-vllm-rocm-gfx1151/0004-rocm-fallback-and-optional-sagemaker-standards.patch` | AMDSMI fallback and optional SageMaker imports affected generic CLI/API startup. | Rebuild and install vLLM, then run `vllm --help`, `vllm --version`, and promoted Gemma/Qwen scenarios without import-time failures. | `docs/patches.md` vLLM |
| pending | Gemma 4 attention | `python-vllm-rocm-gfx1151/0005-rocm-reduce-triton-unified-attention-prefill-tile-for-large-heads.patch` | Large-head ROCm Triton unified-attention prefill could exceed the gfx1151 LDS limit. | Run the promoted Gemma 4 text/server lanes and confirm the large-head prefill path no longer faults; retire if the rebuilt Triton/vLLM lane no longer needs the tile reduction. | `docs/patches.md` vLLM |
| pending | Gemma 4 AITER attention | `python-vllm-rocm-gfx1151/0007-rocm-enable-gfx1x-aiter-and-prefer-it-for-gemma4.patch` | Gemma 4 needed gfx1x AITER discovery and `ROCM_AITER_UNIFIED_ATTN` selection to avoid the earlier Triton unified-attention decode failure. | Run promoted Gemma 4 text/server scenarios and confirm the backend split in scenario logs. | `docs/patches.md` vLLM |
| pending | TorchAO startup | `python-vllm-rocm-gfx1151/0008-torchao-startup-stays-lazy.patch` | Generic vLLM startup surfaced warning noise from a broken external TorchAO package. | Run generic vLLM CLI smokes and TorchAO scenarios after the local TorchAO lane is rebuilt and installed. | `docs/patches.md` vLLM |
| pending | vLLM startup imports | `python-vllm-rocm-gfx1151/0009-cli-startup-stays-runtime-light.patch` | Plain CLI/help paths imported benchmark, OpenAI, Transformers, and runtime command trees eagerly. | Run `vllm --help`, `vllm --version`, and promoted scenarios on the rebuilt stack; confirm no unrelated optional runtime import failures. | `docs/patches.md` vLLM |
| pending | Qwen3.5 hybrid/GDN behavior | `vllm.qwen3_5.0_8b.text.basic` and related Qwen3.6 probes | The repo carries Blackcat Informatics advisory-lane Qwen3.5/GDN behavior, and the local smoke/probe outcomes were recorded before the current native rebuild finished. | Run `vllm.qwen3_5.0_8b.text.basic` and the Qwen3.6 probes after the rebuilt stack is installed; revalidate the behavior, not the upstream/advisory patch source. | `docs/maintainers/current-state.md` |
| pending | Qwen sampler | `python-vllm-rocm-gfx1151/0011-rocm-avoid-triton-topk-topp-sampler.patch` | The Triton top-k/top-p filter faulted on the Qwen3.5-family large-vocabulary logits shape. | Run the Qwen sampler scenario and, if needed, a focused sampler repro against the rebuilt Triton/vLLM stack. | `docs/patches.md` vLLM |
| pending | AITER headers | `python-amd-aiter-gfx1151/0001-gfx1151-rdna35-header-compat.patch` and `0006-rdna35-hip-reduce-wave32-dpp-compat.patch` | gfx1151 builds needed RDNA 3.5 header compatibility for packed ops and wave32/DPP reduction helpers. | Rebuild AITER and run promoted Gemma/Qwen scenarios that import or JIT AITER modules. | `docs/patches.md` AITER |
| pending | AITER installed JIT | `python-amd-aiter-gfx1151/0002-jit-runtime-finds-hipcc-and-user-jit-modules.patch` | Installed systems needed deterministic `hipcc` resolution and user-cache JIT imports. | Run a scenario that imports AITER JIT modules after package install without ambient shell PATH assumptions. | `docs/patches.md` AITER |
| pending | AITER MoE compatibility | `python-amd-aiter-gfx1151/0003-fused-moe-unknown-gfx-falls-back-to-2stage.patch`, `0004-moe-tuner-skips-missing-1stage-asm-metadata.patch`, and `0005-ck-moe-normalizes-zero-splitk-and-forwards-stage2.patch` | gfx1x AITER MoE experiments needed unknown-gfx fallback, missing metadata tolerance, and CK splitk normalization. | Re-run the forced AITER MoE probes only when that lane is intentionally under investigation; keep default Gemma 4 on Triton MoE unless fresh evidence changes the lane. | `docs/patches.md` AITER |
| pending | Gemma 4 accepted lanes | `vllm.gemma4.26b-a4b.text.basic` and `vllm.gemma4.26b-a4b.server.basic` | The earlier accepted Gemma 4 26B-A4B lanes passed before the current native rebuild finished. | Run both scenarios against the rebuilt installed stack and record model binding, backend split, outputs, and run durations. | `docs/maintainers/current-state.md` |
| pending | Gemma 4 E2B server fault | `vllm.gemma4.e2b.server.*` non-exploratory and kernel-probe scenarios | E2B server/AsyncLLM initialization faulted on ROCm, including a forced Triton-attention probe. | Re-run the non-exploratory E2B server scenarios and the forced-attention probe after the rebuilt stack is installed; promote, retire, or narrow the failure. | `docs/maintainers/current-state.md` |
| pending | Gemma 4 compiled E2B path | `vllm.gemma4.e2b.text.compiled` | The compiled+cudagraph path initialized but generated corrupted text; an earlier no-cudagraph compiled probe faulted during warmup. | Re-run the compiled E2B probe after the rebuilt stack is installed and keep it exploratory unless it produces the expected output. | `docs/maintainers/current-state.md` |
| pending | Gemma 4 multimodal warmup | Gemma 4 multimodal server scenarios and 26B-A4B text-only limits | Multimodal warmup could trigger ROCm GPU memory faults when text-only limits were incomplete or when E2B server initialized encoder caches. | Re-run representative multimodal exploratory scenarios and confirm promoted text-only lanes still zero `image`, `audio`, and `video`. | `docs/maintainers/current-state.md` |
| pending | Qwen3.6 blocked probe | `vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-no-aiter-blocked` | The non-AITER FP8 MoE path reported no backend support for gfx1151. | Run the blocked probe after the rebuilt stack is installed and confirm the same backend-selection failure class. | `docs/maintainers/current-state.md` |
| pending | Qwen3.6 forced AITER probe | `vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-aiter-blocked` | The forced AITER path reached `module_quant` and failed on `mfma_adaptor`. | Run the blocked probe after the rebuilt stack is installed and confirm the same or updated AITER feature-gap signature. | `docs/maintainers/current-state.md` |
| pending | Qwen3.5 smoke and sampler | `vllm.qwen3_5.0_8b.text.basic` and the sampler fallback finding | Qwen3.5 0.8B failed after model forward on the Triton top-k/top-p sampler, then passed with the PyTorch fallback patch before the current native rebuild finished. | Re-run `vllm.qwen3_5.0_8b.text.basic` and any focused sampler repro needed to confirm the failure remains fixed. | `docs/maintainers/current-state.md` |
| pending | TorchAO runtime lane | Local `python-torchao-rocm-gfx1151` plus vLLM TorchAO probes | Generic startup was separated from actual TorchAO quantization behavior, and some real-model probes remained exploratory. | Rebuild and install TorchAO and vLLM, then run tiny and selected real-model TorchAO scenarios. | `docs/maintainers/current-state.md` |
| pending | vLLM build-path sanitizer experiment | Backlog item for HIP prefix-map forwarding through quoted `CMAKE_ARGS` | A trial fix routed prefix maps into HIP builds but made `csrc/sampler.hip` fail on gfx1151 with `Invalid dpp_ctrl value`. | Re-test only after the rebuilt ROCm compiler/Triton/vLLM lane is installed; keep it as a deferred blocker if the compile failure reproduces. | `docs/backlog.md` |

## Applied Patch Carry Skipped From Revalidation

These applied source patches or patch classes are not in the pending table
because the repo can rule out the self-hosted dependency rebuild as the reason
for their current shape, or because they are upstream/recipe-derived carry
rather than local-origin runtime findings.

| Scope | Patch or class | Reason |
| --- | --- | --- |
| Lemonade | `lemonade-server/0001` through `0004` | Local policy and presentation changes for NPU probing and system-managed backends; the local-repo rebuild does not make these unnecessary. |
| vLLM | `0001-python-3.14-version-gates.patch` | Python-version build compatibility, validated by package build/tests rather than runtime dependency freshness. |
| vLLM | `0006-setup.py-forward-host-and-hip-flags-into-cmake.patch` when used only for source-path sanitation | Build hygiene for Arch prefix maps and Strix tuning flags; not an inference failure that stale runtime deps can explain. Runtime consequences remain covered by promoted smoke tests. |
| vLLM | `0010-rocm-support-qwen35-hybrid-gdn.patch` | Carries Blackcat Informatics advisory-lane behavior. The patch itself is not local-origin revalidation scope, but Qwen3.5/Qwen3.6 scenario outcomes remain pending above. |
| PyTorch | `0001-setup-allow-skipping-build-deps.patch` and `0002-use-wide-magma-version-encoding.patch` | Package build and toolchain compatibility around Arch Python/CMake/MAGMA, not downstream inference behavior plausibly fixed by rebuilding against local packages. |
| TorchVision | `0001-setup-relative-sources.patch` | Build-path sanitation for ROCm HIP sources; validated by package-local build/path checks. |
| TorchAO | `0001-setup.py-honor-pytorch-rocm-arch.patch` | Build target selection for ROCm source builds; a full local dependency rebuild does not remove the need to avoid upstream's hard-coded `gfx942`. |
| orjson | `0001-cold-path-feature-check-uses-rustc-capability.patch` | Rust compiler capability detection, not ROCm/local-stack runtime behavior. |
| Recipe dynamic patches | Patches rendered directly from Blackcat Informatics recipe inputs or distilled from recipe dynamic-patching scripts | These are upstream/recipe inputs; revalidate only local runtime findings that remain documented outside the upstream recipe itself. |

## Accepted Item Classes Not Quarantined

The following categories are not blocked by this ledger unless a post-rebuild
run produces new contradictory evidence:

- package policy and metadata decisions that do not depend on runtime behavior
- Python version compatibility patches validated by package build/test results
- Lemonade system-managed backend policy patches
- baseline package selection and recipe provenance documentation
