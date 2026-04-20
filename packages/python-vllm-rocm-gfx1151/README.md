# python-vllm-rocm-gfx1151

## Maintenance Snapshot

- Recipe package key: `vllm`
- Scaffold template: `python-project-vllm`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/vllm-project/vllm.git`
- Derived pkgver seed: `0.19.1.r8.d20260317.gad42886`
- Recipe steps: `19, 20, 21, 22, 23, 24`
- Recipe dependencies: `pytorch, triton, aotriton`
- Recorded reference packages: `aur/python-vllm`
- Authoritative reference package: `aur/python-vllm`
- Advisory reference packages: `none`
- Applied source patch files/actions: `38`

## Recipe notes

Upstream vLLM (not ROCm fork). AITER integration comes from
PyTorch's third_party/aiter/ which has full gfx1151 support.

Build attempts AITER first (VLLM_ROCM_USE_AITER=1). If AITER
compilation fails, falls back to Triton-only build. Result is
recorded in .aiter-status file ("enabled" or "disabled").

## Scaffold notes

- There does not appear to be a current dedicated python-vllm-rocm AUR package; the closest package baseline is the generic AUR python-vllm package, with ROCm-specific integration coming from this recipe.
- Use the latest stable upstream release tarball (v0.19.1) instead of a floating full Git clone. Upstream released v0.19.1 as a patch release on top of v0.19.0, so the package now follows the final stable tag rather than the earlier v0.19.1 release candidate.
- The v0.19.1 impact review found no dropped local patch lane: upstream mainly added Gemma 4 model/tooling coverage, relaxed the Transformers 5.x upper-bound shape while excluding known bad 5.x minors, and bumped compressed-tensors. The carried local patches were refreshed against the final tag and the build produced `python-vllm-rocm-gfx1151-0.19.1.r8.d20260317.gad42886-1-x86_64.pkg.tar.zst`.
- This scaffold carries the minimal Python-3.14 source patch needed to build from the stable tarball: relax the Python upper bound and extend the hard-coded CMake supported-version list through 3.14.
- Carries a package-local CLI import patch so vllm --version remains a metadata-only path instead of importing optional OpenAI and Triton runtime modules at startup.
- Carries a ROCm-specific Triton compatibility patch so the vendored triton_kernels tree is treated as unavailable when the installed Triton runtime lacks CUDA-only APIs such as triton.language.target_info or triton.constexpr_function.
- Carries a ROCm-platform fallback patch so Strix Halo can fall back from AMDSMI ASIC-info lookup to torch.cuda without tripping the import-time warning_once circular import path.
- Carries an optional-SageMaker patch so vllm --help and the base OpenAI server routes stay usable when model_hosting_container_standards is not installed.
- Carries a ROCm Triton unified-attention tile-size patch so large-head prefill paths such as Gemma 4 global attention do not request more than 64 KiB of LDS/shared memory on gfx1151.
- Carries a setup.py flag-forwarding patch so host CFLAGS/CXXFLAGS and HIPFLAGS are passed into the CMake ROCm extension build explicitly. This keeps Arch prefix-map sanitization and Strix tuning flags active in the shipped HIP extension modules.
- Disables LTO for this package. Re-enabling inherited -flto=* flags makes ROCm shared-module links such as _moe_C.abi3.so and _rocm_C.abi3.so fail with `LLVM gold plugin has failed to create LTO module: Invalid record`.
- Carries a gfx1x AITER enablement patch and a Gemma 4 backend-selection patch so heterogeneous-head Gemma 4 models can prefer ROCM_AITER_UNIFIED_ATTN on Strix Halo instead of forcing the Triton unified-attention backend that currently miscompiles during decode.
- Carries a Qwen3.5 hybrid/GDN patch that keeps AMD FLA autotune away from gfx1151 page-faulting shapes, preserves hybrid block-size alignment after ROCm platform updates, and routes hybrid full-attention layers away from AITER attention because Qwen3.5/GDN can choose non-power-of-2 block sizes.
- Does not carry the broader fused-MoE default-policy flip, and no longer carries the dormant Gemma 4 AITER-only MoE padding patch. The 2026-04-17 reference-host text/basic-server validation used AITER unified attention but `Using TRITON backend for Unquantized MoE`, so the durable carry stays limited to the host-proven lane.
- The current repo-owned `google/gemma-4-26B-A4B-it` validation lane is tracked through `tools/gemma4_text_smoke.py` and `tools/gemma4_server_smoke.py`. It is text-only basic serving with `--limit-mm-per-prompt {"image":0,"audio":0,"video":0}`, `--max-model-len 128`, `--max-num-batched-tokens 32`, and a 420-second server startup timeout. After installing the repaired Triton package on 2026-04-19, the tracked offline text compiled probe passed with AITER unified attention, TRITON unquantized MoE, torch.compile, and CUDAGraph capture. Do not generalize that to E2B: the installed-Triton E2B compiled+cudagraph probe initialized and generated corrupted text, and the earlier no-cudagraph E2B compiled probe faulted the GPU during initialization/warmup.
- The 2026-04-19 26B-A4B MoE backend probes passed for default/automatic MoE and forced `--moe-backend triton`, both with `Using TRITON backend for Unquantized MoE`; forced `--moe-backend aiter` failed fast with `ValueError: ROCm AITer MoE backend is not available for this configuration`. Treat TRITON unquantized MoE as the maintained sparse MoE lane.
- The wider Gemma 4 scenario matrix is tracked under `inference/scenarios/vllm-gemma4.toml`. Broad scenario selections skip entries tagged `exploratory` by default, so multimodal, remaining compiled-path, forced-MoE-backend experiments, and real-model TorchAO probes stay opt-in unless a reference-host run explicitly promotes them.
- The E2B server scenario matrix also has a tracked forced-attention probe for `--attention-backend TRITON_ATTN`. On 2026-04-19 it proved vLLM selected `Using TRITON_ATTN backend` and still reproduced the server/AsyncLLM GPU memory-access fault, so the current E2B server fault is not explained by AITER unified attention alone.
- The E2B multimodal server scenarios are blocked by the same server/AsyncLLM initialization fault rather than by their request payloads. On 2026-04-19, `vllm.gemma4.e2b.server.image` selected `ROCM_AITER_UNIFIED_ATTN`, loaded weights, started encoder-cache profiling with 29 maximum-size image items, and then hit a ROCm GPU memory-access fault before serving the image request.
- Depends on the local python-transformers-gfx1151 closure package rather than the distro python-transformers lane because Gemma 4 support first appears in upstream transformers 5.5.x and the older host package did not ship transformers.models.gemma4.
- Depends on the local python-mistral-common-gfx1151 closure package rather than the stale host python-mistral-common 1.8.x lane because Transformers 5.5.x imports ReasoningEffort from mistral_common.protocol.instruct.request.
- Carries a merged TorchAO startup-laziness patch so generic vLLM startup paths keep TorchAO version checks metadata-only and only import `TorchAOConfig` when `quantization == torchao`. This keeps optional broken host python-torchao-rocm packages from surfacing warning noise on unrelated code paths.
- Carries a merged CLI/runtime-light startup patch so plain `vllm --help` stays off the benchmark latency tree, OpenAI chat-utils tool-call path, Transformers-backed `arg_utils` helpers, and heavy `serve`/`launch`/`run-batch` runtime imports unless the user actually selected those flows.
- Carries a ROCm top-k/top-p sampler guard so large-vocabulary Qwen3.5-family runs use vLLM's existing PyTorch filtering fallback instead of the Triton filter path that faulted the GPU on gfx1151.
- The reference host now uses the local python-torchao-rocm-gfx1151 replacement lane, so the old external python-torchao-rocm failure is historical rather than current state. Generic vLLM startup should still stay TorchAO-clean on non-TorchAO code paths, and the tracked helpers for actual --quantization torchao support remain tools/torchao_vllm_smoke.py plus the Gemma 4 TorchAO scenarios.
- `tools/torchao_vllm_smoke.py` now covers the tiny no-download checkpoint, a serialized real-model probe, and a real-model online quantization path. On 2026-04-19, `vllm.gemma4.e2b.torchao.online-real-model` passed on the reference host with `quantization=torchao`, `ROCM_AITER_UNIFIED_ATTN`, and 10.62 GiB model-loading memory. Keep the serialized real-model scenario exploratory: it now writes processor files correctly, but still fails in TorchAO/vLLM weight loading with `AttributeError: 'Tensor' object has no attribute 'tensor_data_names'`.
- makepkg -e reuses src/, so build() intentionally reapplies the carried source patches before wheel generation instead of assuming prepare() already ran in the current tree.
- makepkg -f can also reuse a partially patched src/ tree across failed iterations. The PKGBUILD now re-extracts v0.19.1.tar.gz and reapplies the full carried patch series on a known-clean tree whenever its source-patch sentinels are missing, instead of relying on per-patch stamp files under src/.patch-state.
- Preserve makepkg's inherited CFLAGS/CXXFLAGS when layering Strix tuning flags, and feed the same prefix-map flags into HIPFLAGS, so Arch's build-path sanitization survives the ROCm/HIP compile lane too.
- Upstream openai-harmony is a small Rust/PyO3 helper library with published manylinux wheels, not a ROCm-specific component. If Arch still lacks an official package, the right local story is a closure package derived from aur/python-openai-harmony. If this repo ingests it locally, it should still inherit the normal Strix build lane for applicable native code: Zen 5 / znver5 CPU tuning, -O3 or equivalent, LTO when compatible, and PGO when the build system exposes a maintainable path.
- Do not treat a successful build as sufficient for system-Python cutover; the gate is a real vLLM smoke test after the TheRock ROCm split packages are installed coherently.
- Keep the gfx1151 ROCm/AITER recipe patches in the source package, but evaluate Python-3.14 compatibility separately from ROCm runtime/linker issues.
- The earlier numba-pin idea is not currently part of the actual built package story; treat any numba change as a separate follow-up until it is backed by a real source patch.

## Intentional Divergences

- This package is ROCm-specific even though the closest Arch-family baseline is the generic aur/python-vllm package.
- Carries a deliberate Python-3.14 compatibility delta and recipe-specific ROCm/AITER integration that are not part of the generic baseline.
- Carries repo-owned Gemma 4 validation lanes for Strix Halo because the host-proven path is narrower than upstream defaults: AITER unified attention, TRITON unquantized MoE, text-only multimodal limits, and per-checkpoint eager/compiled decisions.
- Carries a repo-owned Qwen3.5 hybrid/GDN patch lane for the parts of Blackcat Informatics' advisory recipe that are still missing from the maintained vLLM 0.19.1 package source.

## Update Notes

- Check upstream vllm release notes and pyproject metadata first, then reconcile the Python upper-bound and hard-coded supported-version list with the current state of Python 3.14 support.
- For the v0.19.1 upgrade, the upstream v0.19.0..v0.19.1 tarball diff was mostly additive (82 files changed, 5061 insertions, 269 deletions). The impact review focused on dependency metadata (`transformers` and `compressed-tensors` constraints), Gemma 4 model/tooling additions, and the local patch touchpoints; the carried ROCm/platform, Qwen3.5/GDN, sampler, and startup-laziness patches still apply after refresh.
- When validating a new model, usage pattern, or stable-tag gap, scout upstream release notes, open issues, open PRs, and recent commits before freezing local patch carry. Gemma 4 needed exactly that: the durable fixes were the unified-attention backend selection and server/template follow-ups, while the earlier AITER fused-MoE carries were later pruned once the validated default lane stayed on TRITON MoE.
- If numba remains part of the Python 3.14 story, capture it as a real source patch or package dependency decision rather than a no-op scripted edit.
- Keep vllm --version as a metadata-only smoke path. If upstream CLI imports optional OpenAI or Triton modules eagerly again, prefer restoring a lazy import boundary over adding unrelated hard runtime dependencies just for version output.
- Treat openai-harmony as a normal runtime-closure package, not an optdepend, if this repo wants GPT-OSS/Harmony paths to work. The current AUR baseline is a good starting point, but it omits the upstream python-pydantic runtime dependency and should not be copied blindly. The reason to package it locally is closure and metadata correctness, not a ROCm-specific patch lane.
- Keep the local Mistral Common lane new enough to export mistral_common.protocol.instruct.request.ReasoningEffort. The concrete host failure was python-mistral-common 1.8.6-1, which was too old for the current Transformers/Gemma 4 processor path.
- Keep the vendored triton_kernels path gated on the installed Triton runtime rather than forcing python-triton-gfx1151 to emulate CUDA-only APIs such as triton.language.target_info. On this ROCm lane, treat unavailable vendored Triton kernels as a clean fallback, not as a hard runtime error.
- Keep the ROCm large-head unified-attention prefill tile reduction unless upstream vLLM or Triton lands a fix for the 64 KiB LDS overflow. The concrete host failure was Gemma 4 global attention on gfx1151 requesting 66560 bytes of shared memory from the Triton 2D unified-attention kernel.
- Keep the setup.py compiler-flag forwarding patch unless upstream starts passing CFLAGS/CXXFLAGS/HIPFLAGS into the CMake ROCm build itself. The concrete packaging failure was $srcdir leaking into shipped extension modules because the HIP lane was built without Arch prefix-map flags.
- Keep LTO disabled for this package unless the ROCm HIP shared-module link path becomes compatible with it. The concrete host failure was _moe_C.abi3.so / _rocm_C.abi3.so link failure with `LLVM gold plugin has failed to create LTO module: Invalid record`.
- Keep the gfx1x AITER enablement and Gemma 4 ROCM_AITER_UNIFIED_ATTN preference unless upstream lands a ROCm-safe single-backend path for heterogeneous-head Gemma 4 models. The concrete host failure was successful Gemma 4 initialization followed by Triton unified-attention decode miscompilation (`operation scheduled before its operands`) and garbage output on gfx1151.
- Keep `0007-rocm-enable-gfx1x-aiter-and-prefer-it-for-gemma4.patch` limited to gfx1x AITER support plus the Gemma 4 backend override, and do not reintroduce the broader fused-MoE default flip unless fresh host validation across real ROCm models proves it safe. The 2026-04-17 reference-host `google/gemma-4-26B-A4B-it` text smoke faulted the GPU when that policy forced the AITER fused-MoE 2-stage path without an explicit runtime override.
- Keep the repo-owned Gemma 4 text-only smoke lanes on `enforce_eager=True` / `--enforce-eager` until separate host validation proves the compiled/cudagraph ROCm path is clean for each promoted checkpoint. vLLM documents eager mode as disabling compilation and cudagraph capture, so treat relaxing it as a follow-up performance lane rather than a silent default change. After installing the repaired Triton package on 2026-04-19, `google/gemma-4-26B-A4B-it` passed the tracked offline text compiled probe with AITER unified attention, TRITON unquantized MoE, torch.compile, and CUDAGraph capture. The same installed-Triton pass did not promote `google/gemma-4-E2B-it`: compiled+cudagraph initialized and generated, but returned corrupted text instead of the expected five-word answer; a no-cudagraph E2B compiled probe had previously faulted the GPU during initialization/warmup.
- Keep Gemma 4 26B-A4B server startup timeouts long enough for cold reference-host loads. A 300-second budget killed the server while it was still loading safetensors shards; the helper now defaults this constrained 26B-A4B lane to 420 seconds.
- Use the tracked `compiled-probe`, `kernel-probe`, `multimodal`, and `quantization-probe` scenario tags for future investigations instead of adding terminal-only one-offs; keep `exploratory` on any scenario that should not run as part of broad package validation.
- Keep `0010-rocm-support-qwen35-hybrid-gdn.patch` until upstream vLLM lands equivalent ROCm-safe Qwen3.5/GDN handling. The patch carries the still-missing pieces from Blackcat Informatics' advisory lane: AMD-restricted FLA autotune grids, float32 GDN exponent operands, GDN warmup at T=64 only, hybrid block-size realignment after ROCm platform updates, and hybrid full-attention fallback away from AITER attention. In vLLM 0.19.1, the GDN warmup loop still lives in `vllm/model_executor/layers/mamba/gdn_linear_attn.py`, not the older advisory `qwen3_next.py` path.
- Do not restore the dropped Gemma 4 ROCm AITER MoE intermediate-padding carry unless a future explicit AITER fused-MoE lane reproduces a real alignment failure after the AITER backend is re-enabled on purpose. The 2026-04-17 validated reference-host lane used TRITON backend for Unquantized MoE, so that patch was removed as dormant carry. The 2026-04-19 forced AITER MoE server probe failed earlier with `ValueError: ROCm AITer MoE backend is not available for this configuration`, while default/automatic and forced Triton MoE server probes passed.
- Keep Gemma 4 text-only serving fully text-only by zeroing `image`, `audio`, and `video` in `--limit-mm-per-prompt`. The concrete Gemma 4 26B-A4B server failure was vLLM still entering multimodal warmup and then faulting the GPU during engine initialization when `video` remained implicit.
- Keep TorchAO version checks metadata-only on generic startup paths unless upstream reorganizes its quantization imports. The concrete host failure was an external python-torchao-rocm package whose optional _C.abi3.so extension was both missing a usable torch/lib runpath and built against an incompatible PyTorch ABI, causing warning noise during unrelated vLLM startup when vLLM imported the TorchAO quantization module just to ask a version question.
- Keep the merged TorchAO startup-laziness patch intact unless upstream reorganizes its quantization imports. That carry now covers both metadata-only version checks and quantization-registry lazy imports, which are jointly required to keep generic startup paths off the full TorchAO module unless `quantization == "torchao"`.
- Keep the merged CLI/runtime-light startup patch intact unless upstream makes the generic startup path import-clean on its own. That carry now keeps plain `vllm --help` off the benchmark tree, OpenAI chat-utils path, Transformers-backed `arg_utils` helpers, and the heavy shared runtime command imports.
- Keep the ROCm top-k/top-p sampler patch unless upstream or the local Triton lane proves `apply_top_k_top_p_triton` safe for large Qwen-family vocabularies on gfx1151. The 2026-04-19 standalone repro faulted the GPU with logits shaped `(32, 248320)`, top-k enabled, and top-p `0.9`, while vLLM's existing PyTorch fallback completed on the same tensor.
- Treat `Qwen/Qwen3.6-35B-A3B-FP8` as a blocked FP8 MoE probe, not a passing smoke, until a ROCm/gfx1151 FP8 MoE backend exists. With AITER disabled, vLLM reports `No FP8 MoE backend supports the deployment configuration`; the Triton and batched Triton FP8 MoE gates only advertise ROCm FP8 support for gfx9, not gfx1151.
- Keep patch application idempotent across reused src/ trees. The concrete host failure while cutting pkgrel=14 was a file-adding patch aborting in `prepare()` after a previous failed build left a partially patched source tree behind.
- Keep the inherited makepkg compile flags when layering Strix tuning flags. Overwriting CFLAGS/CXXFLAGS drops Arch's build-path prefix maps and can leak $srcdir paths into the shipped ROCm extension modules.
- Keep HIP build-path prefix-map flags explicit and forwarded through setup.py. The ROCm extension build does not automatically inherit the host C/C++ prefix-map settings into CMAKE_HIP_FLAGS, so sanitization has to be carried through HIPFLAGS and then bridged into CMake.
- Keep SageMaker integration optional unless this repo intentionally packages model_hosting_container_standards; missing SageMaker helpers should disable only SageMaker-specific routes, not the base CLI or local server startup paths.
- Keep the ROCm GCN-arch fallback import-safe on Strix Halo. AMDSMI ASIC-info probes can fail even when the device is visible; that must degrade to torch.cuda probing rather than crashing during module import.
- Treat the current external python-torchao-rocm _C-extension failure as a host-package defect, not a blocker for this vLLM lane. Generic startup should stay clean after the local TorchAO-import patch, and the remaining follow-up only matters if this repo needs actual TorchAO custom ops or torchao-backed serving paths that truly require the native extension.
- Treat runtime validation against the live ROCm stack as mandatory; a successful wheel build is not enough.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
