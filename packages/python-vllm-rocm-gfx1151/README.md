# python-vllm-rocm-gfx1151

## Maintenance Snapshot

- Recipe package key: `vllm`
- Scaffold template: `python-project-vllm`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/vllm-project/vllm.git`
- Derived pkgver seed: `0.19.0.r8.d20260317.gad42886`
- Recipe steps: `19, 20, 21, 22, 23, 24`
- Recipe dependencies: `pytorch, triton, aotriton`
- Recorded reference packages: `aur/python-vllm`
- Authoritative reference package: `aur/python-vllm`
- Advisory reference packages: `none`
- Applied source patch files/actions: `30`

## Recipe notes

Upstream vLLM (not ROCm fork). AITER integration comes from
PyTorch's third_party/aiter/ which has full gfx1151 support.

Build attempts AITER first (VLLM_ROCM_USE_AITER=1). If AITER
compilation fails, falls back to Triton-only build. Result is
recorded in .aiter-status file ("enabled" or "disabled").

## Scaffold notes

- There does not appear to be a current dedicated python-vllm-rocm AUR package; the closest package baseline is the generic AUR python-vllm package, with ROCm-specific integration coming from this recipe.
- Use the latest stable upstream release tarball (v0.19.0) instead of a floating full Git clone. Upstream currently exposes a 0.19.1 release candidate but not a final 0.19.1 release, so the stable tag is the safer packaging baseline.
- This scaffold carries the minimal Python-3.14 source patch needed to build from the stable tarball: relax the Python upper bound and extend the hard-coded CMake supported-version list through 3.14.
- Carries a package-local CLI import patch so vllm --version remains a metadata-only path instead of importing optional OpenAI and Triton runtime modules at startup.
- Carries a ROCm-specific Triton compatibility patch so the vendored triton_kernels tree is treated as unavailable when the installed Triton runtime lacks CUDA-only APIs such as triton.language.target_info or triton.constexpr_function.
- Carries a ROCm-platform fallback patch so Strix Halo can fall back from AMDSMI ASIC-info lookup to torch.cuda without tripping the import-time `warning_once` circular import path.
- Carries an optional-SageMaker patch so `vllm --help` and the base OpenAI server routes stay usable when `model_hosting_container_standards` is not installed.
- Carries a ROCm Triton unified-attention tile-size patch so large-head prefill
  paths such as Gemma 4 global attention do not request more than 64 KiB of
  LDS/shared memory on gfx1151.
- Carries a setup.py flag-forwarding patch so host `CFLAGS`/`CXXFLAGS` and
  `HIPFLAGS` are passed into the CMake ROCm extension build explicitly. This
  keeps Arch prefix-map sanitization and Strix tuning flags active in the
  shipped HIP extension modules.
- Disables LTO for this package. Re-enabling inherited `-flto=*` flags makes
  ROCm shared-module links such as `_moe_C.abi3.so` and `_rocm_C.abi3.so`
  fail with `LLVM gold plugin has failed to create LTO module: Invalid record`.
- Carries a gfx1x AITER enablement patch and a Gemma 4 backend-selection patch
  so heterogeneous-head Gemma 4 models can prefer
  `ROCM_AITER_UNIFIED_ATTN` on Strix Halo instead of forcing the Triton
  unified-attention backend that currently miscompiles during decode.
- Carries a TorchAO-import patch so generic vLLM startup paths do not import
  the full TorchAO quantization module just to check an installed version.
  This keeps optional broken host `python-torchao-rocm` packages from emitting
  startup warning noise on non-TorchAO code paths.
- Carries a follow-up TorchAO-registry patch so the quantization registry only
  imports `TorchAOConfig` when `torchao` quantization is actually requested.
  Generic config-validation and CLI/help flows still probe the quantization
  registry, so this second lazy-import boundary is required to suppress the
  same host warning completely.
- Carries a follow-up CLI-help patch so plain `vllm --help` does not eagerly
  import the benchmark command tree. The benchmark latency subcommand imports
  `EngineArgs` at module import time, which can still reach model/quantization
  setup and surface optional TorchAO warning noise even after the two
  TorchAO-specific lazy-import patches.
- Depends on the local `python-transformers-gfx1151` closure package rather than
  the distro `python-transformers` lane because Gemma 4 support first appears
  in upstream `transformers 5.5.x` and the older host package did not ship
  `transformers.models.gemma4`.
- Depends on the local `python-mistral-common-gfx1151` closure package rather
  than the stale host `python-mistral-common 1.8.x` lane because Transformers
  `5.5.x` imports `ReasoningEffort` from
  `mistral_common.protocol.instruct.request`, and that symbol is missing from
  the older package.
- The currently installed external `python-torchao-rocm` package is still not
  import-clean at the native extension layer on this host, but generic vLLM
  startup should no longer import TorchAO eagerly on non-TorchAO code paths.
  Treat the remaining host TorchAO breakage as an optional-feature defect to
  revisit only if this repo needs working TorchAO custom ops or actual
  `--quantization torchao` support.
- makepkg -e reuses src/, so build() intentionally reapplies the carried source patches before wheel generation instead of assuming prepare() already ran in the current tree.
- `makepkg -f` can also reuse a partially patched `src/` tree across failed
  iterations, so patch application is tracked with per-patch stamp files under
  `src/.patch-state`. Keep that idempotency layer unless the package starts
  forcing a clean source tree for every build.
- Preserve makepkg's inherited `CFLAGS`/`CXXFLAGS` when layering Strix tuning
  flags, and feed the same prefix-map flags into `HIPFLAGS`, so Arch's
  build-path sanitization survives the ROCm/HIP compile lane too.
- Upstream openai-harmony is a small Rust/PyO3 helper library with published manylinux wheels, not a ROCm-specific component. If Arch still lacks an official package, the right local story is a closure package derived from aur/python-openai-harmony. If this repo ingests it locally, it should still inherit the normal Strix build lane for applicable native code: Zen 5 / znver5 CPU tuning, -O3 or equivalent, LTO when compatible, and PGO when the build system exposes a maintainable path.
- Do not treat a successful build as sufficient for system-Python cutover; the gate is a real vLLM smoke test after the TheRock ROCm split packages are installed coherently.
- Keep the gfx1151 ROCm/AITER recipe patches in the source package, but evaluate Python-3.14 compatibility separately from ROCm runtime/linker issues.
- The earlier numba-pin idea is not currently part of the actual built package story; treat any numba change as a separate follow-up until it is backed by a real source patch.

## Intentional Divergences

- This package is ROCm-specific even though the closest Arch-family baseline is the generic aur/python-vllm package.
- Carries a deliberate Python-3.14 compatibility delta and recipe-specific ROCm/AITER integration that are not part of the generic baseline.

## Update Notes

- Check upstream vllm release notes and pyproject metadata first, then reconcile the Python upper-bound and hard-coded supported-version list with the current state of Python 3.14 support.
- If numba remains part of the Python 3.14 story, capture it as a real source patch or package dependency decision rather than a no-op scripted edit.
- Keep vllm --version as a metadata-only smoke path. If upstream CLI imports optional OpenAI or Triton modules eagerly again, prefer restoring a lazy import boundary over adding unrelated hard runtime dependencies just for version output.
- Treat openai-harmony as a normal runtime-closure package, not an optdepend, if this repo wants GPT-OSS/Harmony paths to work. The current AUR baseline is a good starting point, but it omits the upstream python-pydantic runtime dependency and should not be copied blindly. The reason to package it locally is closure and metadata correctness, not a ROCm-specific patch lane.
- Keep the local Transformers lane new enough to ship `transformers.models.gemma4`.
  The concrete host failure was a stale `python-transformers 5.2.0-1` package
  that did not recognize `model_type: gemma4`.
- Keep the local Mistral Common lane new enough to export
  `mistral_common.protocol.instruct.request.ReasoningEffort`. The concrete
  host failure was `python-mistral-common 1.8.6-1`, which let Gemma 4 load all
  the way through model weights before processor initialization failed.
- Keep the vendored triton_kernels path gated on the installed Triton runtime rather than forcing python-triton-gfx1151 to emulate CUDA-only APIs such as triton.language.target_info. On this ROCm lane, treat unavailable vendored Triton kernels as a clean fallback, not as a hard runtime error.
- Keep the ROCm large-head unified-attention prefill tile reduction unless
  upstream vLLM or Triton lands a fix for the 64 KiB LDS overflow. The concrete
  host failure was Gemma 4 global attention on gfx1151 requesting 66560 bytes
  of shared memory from the Triton 2D unified-attention kernel.
- Keep the setup.py compiler-flag forwarding patch unless upstream starts
  passing `CFLAGS`/`CXXFLAGS`/`HIPFLAGS` into the CMake ROCm build itself.
  The concrete packaging failure was `$srcdir` leaking into shipped extension
  modules because the HIP lane was built without Arch prefix-map flags.
- Keep LTO disabled for this package unless the ROCm HIP shared-module link
  path becomes compatible with it. The concrete host failure was
  `_moe_C.abi3.so` / `_rocm_C.abi3.so` link failure with
  `LLVM gold plugin has failed to create LTO module: Invalid record`.
- Keep the gfx1x AITER enablement and Gemma 4 ROCM_AITER_UNIFIED_ATTN
  preference unless upstream lands a ROCm-safe single-backend path for
  heterogeneous-head Gemma 4 models. The concrete host failure was successful
  Gemma 4 initialization followed by Triton unified-attention decode
  miscompilation (`operation scheduled before its operands`) and garbage output
  on gfx1151.
- Keep TorchAO version checks metadata-only on generic startup paths unless
  upstream reorganizes its quantization imports. The concrete host failure was
  an external `python-torchao-rocm` package whose optional `_C.abi3.so`
  extension was both missing a usable `torch/lib` runpath and built against an
  incompatible PyTorch ABI, causing warning noise during unrelated vLLM
  startup when vLLM imported the TorchAO quantization module just to ask a
  version question.
- Keep the quantization registry importing `TorchAOConfig` lazily unless
  upstream stops probing every quantization backend during generic config
  validation. The concrete host failure after the first TorchAO patch was
  `vllm --help` still importing `vllm.model_executor.layers.quantization`
  and then pulling in `.torchao` through `get_quantization_config()`.
- Keep the benchmark CLI tree off the plain top-level help path unless
  upstream makes `vllm.entrypoints.cli.benchmark.latency` import-clean on
  generic startup. The concrete host failure after the second TorchAO patch
  was `vllm --help` still emitting the warning because CLI setup imported the
  benchmark latency subcommand just to register `bench`.
- Keep the inherited makepkg compile flags when adding Strix tuning flags.
  Overwriting `CFLAGS`/`CXXFLAGS` drops Arch's build-path prefix maps and can
  leak `$srcdir` paths into the shipped ROCm extension modules.
- Keep HIP build-path prefix-map flags explicit and forwarded through setup.py.
  The ROCm extension build does not automatically inherit the host C/C++
  prefix-map settings into `CMAKE_HIP_FLAGS`, so sanitization has to be carried
  through `HIPFLAGS` and then bridged into CMake.
- Keep SageMaker integration optional unless this repo intentionally packages `model_hosting_container_standards`; missing SageMaker helpers should disable only SageMaker-specific routes, not the base CLI or local server startup paths.
- Keep the ROCm GCN-arch fallback import-safe on Strix Halo. AMDSMI ASIC-info probes can fail even when the device is visible; that must degrade to `torch.cuda` probing rather than crashing during module import.
- Treat the current external `python-torchao-rocm` `_C`-extension failure as
  a host-package defect, not a blocker for this vLLM lane. Generic startup
  should stay clean after the local TorchAO-import patch, and the remaining
  follow-up only matters if this repo needs actual TorchAO custom ops or
  torchao-backed serving paths that truly require the native extension.
- Treat runtime validation against the live ROCm stack as mandatory; a successful wheel build is not enough.
- Keep patch application idempotent across reused `src/` trees. The concrete
  host failure while cutting `pkgrel=14` was `0008` aborting in `prepare()`
  with `torchao_utils.py already exists` after a previous failed build left a
  partially patched source tree behind.
- Follow the official vLLM Gemma 4 recipe for operational behavior, but only
  carry the parts that apply to this local Strix Halo ROCm lane. In practice
  that currently means:
  - use `google/gemma-4-*-it` checkpoints for assistant/chat/reasoning/tool
    smokes; base checkpoints can generate but are not a reliable assistant
    validation target
  - for text-only offline inference, render prompts with
    `tokenizer.apply_chat_template(..., add_generation_prompt=True)` before
    `LLM.generate()` instead of assuming a raw instruction string is a valid
    assistant smoke
  - for text-only serving or benchmarking, prefer
    `--limit-mm-per-prompt image=0,audio=0`; for image-only workloads, prefer
    `--limit-mm-per-prompt audio=0`
  - use `--async-scheduling` for throughput-oriented server runs, and disable
    prefix caching during benchmarks if you want measurements that line up
    with the recipe guidance
  - only apply the Gemma 4 thinking/tool-calling parser flags when the smoke
    or server flow actually exercises those features:
    `--reasoning-parser gemma4`, `--tool-call-parser gemma4`,
    `--enable-auto-tool-choice`, and
    `--chat-template examples/tool_chat_template_gemma4.jinja`

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
