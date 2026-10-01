# Patch Inventory

This page explains the source changes that are important enough to call out by
name. It is a curated map, not the complete patch list.

For the complete applied-patch inventory, inspect:

- `policies/recipe-packages.toml`
- `packages/*/recipe.json`
- `packages/*/PKGBUILD`
- patch files beside the affected package

Runtime-sensitive local-origin patch rationale belongs in this inventory, the
affected package README, `docs/maintainers/current-state.md`, or the tracked
scenario that guards the behavior. Historical quarantine ledgers should not be
the only copy of retained patch rationale.

## Why Patches Live Here

This repo keeps source changes as patch files when a change is expected to
persist, deserves independent review, or may be useful outside this exact host.
Inline shell edits are reserved for narrow packaging mechanics. When behavior
becomes durable, prefer a named patch that another maintainer can review.

## AOCL-LibM

- [SCons compatibility for the Arch amdclang toolchain](../packages/aocl-libm-gfx1151/0001-scons-support-arch-amdclang-toolchain.patch)
  - Keeps macro-redefinition warnings from failing the build while preserving
    AOCL-LibM 5.3's native compiler-feature and linker probes.

## Lemonade

The Lemonade patches apply to the `nisavid/lemonade` fork commit named by the
`lemonade` entry in the `[source_pins]` table of
`policies/recipe-packages.toml`. That fork commit is the fork's upstream
v11.9.0 sync ([nisavid/lemonade#175](https://github.com/nisavid/lemonade/pull/175)),
which contains upstream Lemonade v11.9.0 (`bb39eaf`). At the 11.9.0 repin
([issue 141](https://github.com/nisavid/arch-strix-halo-pkgs/issues/141)),
patches 0001-0004 applied in order with line offsets only and no fuzz, and the
upstream changes to the patched files do not touch the patched hunks, so they
are carried unchanged.

- [Linux NPU fallback when accel-device opens fail](../packages/lemonade-server/0001-linux-npu-fallback-to-pci-id-when-accel-open-fails.patch)
  - Falls back to PCI identification when `/dev/accel/*` probing fails even
    though the hardware is still identifiable from sysfs.
- [Treat packaged HIP and Vulkan `llama.cpp` backends as system-managed](../packages/lemonade-server/0002-llamacpp-external-backends-are-system-managed.patch)
  - Makes Lemonade treat the packaged ROCm and Vulkan `llama.cpp` backends as
    system-managed backends rather than downloadable runtimes, and reads their
    version from `llama-server --version` through an argv-based process call.
  - Lemonade reads `LEMONADE_LLAMACPP_*_BIN` from the environment ahead of
    `config.json` on every backend lookup (still true at 11.9.0). The patch
    therefore no longer carries the config-load environment overlay or the
    CLI backend-table change that older bases needed.
- [Remove the generic `llamacpp:system` backend](../packages/lemonade-server/0003-remove-llamacpp-system-backend.patch)
  - Keeps this custom build focused on the explicit HIP and Vulkan lanes this
    repo packages.
- [Override system-managed `llama.cpp` metadata for packaged backends](../packages/lemonade-server/0004-system-managed-llamacpp-metadata.patch)
  - Makes the Lemonade GUI and backend API report the packaged `llama.cpp`
    revision and upstream `ggml-org/llama.cpp` release URL for the local ROCm
    and Vulkan lanes.
  - It reads `LEMONADE_LLAMACPP_{ROCM,VULKAN}_{VERSION,RELEASE_URL}` only
    from the process environment. From 11.9.0 the package sets them, with the
    `*_BIN` paths, in `/usr/lib/lemonade/llamacpp-gfx1151.env` instead of
    `/etc/lemonade/conf.d/10-llamacpp-gfx1151.conf`, with the same values. Its
    `lemond.service.d/30-env-files.conf` drop-in loads that file after
    conf.d and `/etc/default/lemond`, so a stale owner key cannot shadow it.

Retired: patch 0005, "Merge custom args without keeping quotes", was a
stopgap in `lemonade-server 11.7.0-2` for a fork-only regression. Fork commit
`e3d08ffa6` stacked a second quoting layer on upstream's `keep_quotes=true`
merge
([lemonade-sdk/lemonade#1920](https://github.com/lemonade-sdk/lemonade/pull/1920)),
so llama-server received `'{"preserve_thinking":true}'` for the qwen35 and
qwen35moe `--chat-template-kwargs` architecture default and exited. The fork
fix,
[nisavid/lemonade#168](https://github.com/nisavid/lemonade/issues/168)
(`2cb1a91`, PR 169), is merged into the v11.9.0 sync (`9038fb0`), so the
patch was dropped at the 11.9.0 repin. It would no longer apply there anyway:
upstream moved the merge into `recipe_arg_resolver.h`
([lemonade-sdk/lemonade#3265](https://github.com/lemonade-sdk/lemonade/pull/3265)).
`lemonade.chat.pinned-user-model.qwen35moe` remains the live guard.

## llama.cpp

- [Shared HIP/Vulkan selected-token logits server extension](../patches/llama.cpp-common/0001-server-return-selected-token-logits.patch)
  - Adds a generic `/completion` `token_logits` request field and returns the
    requested raw token logits in the final response as a flat array for the
    first available next-token distribution.
  - Disables backend sampled-candidate logits when `token_logits` is requested
    so every requested token ID is returned from full-vocabulary logits.
  - Handles prompt-final selected logits when `n_predict` leaves no generation
    budget, preserves original token bytes separately from the UTF-8-safe token
    string, and caps requests at 1024 selected token IDs.
  - Keeps model-specific token selection in downstream service configuration
    instead of encoding a rerank model assumption in the backend packages.

## vLLM

- [ROCm local carry re-ported for vLLM 0.30.0](../packages/python-vllm-rocm-gfx1151/0016-rocm-refresh-local-carry-for-vllm-0.30.0.patch)
  - Re-ports the 0.21.0 carry onto upstream vLLM 0.30.0 (`ced6857a`). Of the
    29 per-file sections, 12 are kept (two at moved paths) and 17 are dropped
    as upstream-equivalent, obsolete with Triton 3.8, or AITER-only.
  - Forwards CFLAGS, CXXFLAGS and HIPFLAGS from `setup.py` into the CMake ROCm
    build, and keeps the HIP `vllm_bfloat16` aliases in
    `csrc/libtorch_stable/cuda_vec_utils.cuh`.
  - Keeps `vllm --version` metadata-only and plain `vllm --help` off the serve
    runtime, and keeps SageMaker and TorchAO optional on startup paths.
  - Keeps large-head ROCm prefill paths such as Gemma 4 global attention under
    the gfx1151 LDS/shared-memory limit.
  - Keeps the Qwen3.5/GDN FLA autotune restriction and float32 gate exponents
    on AMD, the large-vocabulary top-k/top-p PyTorch fallback, and the padded
    EAGLE/MTP drafter `valid_count` dtype fix.
  - Keeps CK/direct FlashAttention promotion behind the imported paged-KV
    varlen surface needed by the vLLM engine route.
  - Drops the gfx1x AITER enablement, the Gemma 4 AITER preference and the
    hybrid AITER handling. AITER is off the required gfx1151 path, and Gemma 4
    now selects upstream `TRITON_ATTN`.
  - The current Qwen CK consumer boundary is inside CK paged-KV behavior: the
    normal hybrid path presents 64-token pages, while diagnostics that force
    128-divisible pages progress to a GPU fault. That boundary is documented in
    [FlashAttention CK paged-KV boundary](maintainers/flashattention-ck-paged-kv.md).

## AITER

- [gfx1x fused-MoE experiment compatibility](../packages/python-amd-aiter-gfx1151/0003-fused-moe-unknown-gfx-falls-back-to-2stage.patch)
  - Lets unknown gfx targets fall back to the 2-stage fused-MoE path instead of
    keying directly into missing 1-stage metadata.
- [Missing 1-stage ASM metadata skip](../packages/python-amd-aiter-gfx1151/0004-moe-tuner-skips-missing-1stage-asm-metadata.patch)
  - Lets the MoE tuner skip unavailable 1-stage ASM metadata instead of
    treating it as a hard failure.
- [CK MoE splitk normalization and forwarding](../packages/python-amd-aiter-gfx1151/0005-ck-moe-normalizes-zero-splitk-and-forwards-stage2.patch)
  - Normalizes `splitk` values of `None` or `0` to `1` and forwards the value
    through the CK 2-stage path.
  - These patches are retained for explicit AITER fused-MoE experiments, not as
    evidence that the maintained Gemma 4 lane should leave Triton unquantized
    MoE.

## FlashAttention

- [Initialize CK split-KV forward args](../packages/python-flash-attn-rocm-gfx1151/0010-init-ck-splitkv-args.patch)
  - Value-initializes `fmha_fwd_splitkv_args` and sets `sink_ptr`,
    `sink_size`, and `logits_soft_cap` in the varlen and kvcache split-KV
    argument builders. CK `03ce21dd` added those fields and FlashAttention
    `3f94643f` never set them, so the split-KV kernel dereferenced
    uninitialized host stack as `sink_ptr` and the paged-KV varlen path
    faulted the GPU.
  - Backports the split-KV hunks of upstream `8afc617a` (#2363) and the
    `logits_soft_cap` line from `c661198a`.
    [Patch 0007](../packages/python-flash-attn-rocm-gfx1151/0007-adapt-ck-fwd-args-layout.patch)
    is a partial #2363 backport that covered only `fmha_fwd_args`.
  - The longer-term fix is to move the package to a FlashAttention ref that
    contains `8afc617a`, then drop 0007 and 0010.

## PyTorch

- [Initialize NumPy before ROCm global dependencies](../packages/python-pytorch-opt-rocm-gfx1151/0007-initialize-numpy-before-global-deps.patch)
  - Loads NumPy's OpenBLAS provider before PyTorch loads ROCm global
    dependencies, keeping `import torch` stable on the installed TheRock 7.13
    runtime stack.
- [Enable CK GEMM on gfx1151](../packages/python-pytorch-opt-rocm-gfx1151/0005-enable-ck-gemm-on-gfx1151.patch)
  - Adds gfx1151 to `Context::ckSupported()`. Refreshed at `13da0862`, where
    upstream's list dropped gfx90a and is now `gfx942` and `gfx950`.
- [Do not install the system AOTriton prefix into torch](../packages/python-pytorch-opt-rocm-gfx1151/0010-disable-system-aotriton-install.patch)
  - Removes the `aotriton.cmake` rule that copies `$AOTRITON_INSTALLED_PREFIX`
    `lib` and `include` (the system `/usr`) into `torch/`. Arch carries the
    same hunk as `aotriton_disable_install.patch`.
- The AOTriton 0.12 lazy-tensor callback patch (0009) was dropped at
  `13da0862`, because upstream `LazyTensorFunctions` now handles the 0.12+
  callback shape behind `AOTRITON_VERSION_INT(0, 12)`.

## Triton

- [Python 3.14 and pybind11 build-system compatibility](../packages/python-triton-gfx1151/0001-python-3.14-and-pybind11-build-system.patch)
  - Drops the `cmake==4.0` and `ninja` pins from the root `pyproject.toml`
    build requirements, so the no-isolation build uses Arch's cmake, ninja and
    pybind11.
- [Disable `-Werror` for the packaged build](../packages/python-triton-gfx1151/0002-disable-werror-with-therock-llvm-headers.patch)
  - Keeps warnings from amdclang against the pinned upstream LLVM 5f07f818
    headers from failing the package build.
- The 3.0-era `AttrsDescriptor.__repr__` patch was dropped at Triton 3.8,
  because the class no longer exists and torch 2.12 Inductor takes its dict
  path without it.

## AOTriton

- [Gate vendored Triton NVIDIA build artifacts](../packages/python-aotriton-gfx1151/0001-gate-vendored-triton-nvidia-build-artifacts.patch)
  - Backend-gates the NVIDIA plugin wiring in the vendored hyperjump Triton
    (`db82b800`) and stops it from building the CUDA GSan runtime, which
    AOTriton never uses for gfx1151. The patch is unchanged from 0.12b to
    0.13b because both releases pin the same Triton commit.
- The old `c44b870b` Python 3.14 `ast.Num` cherry-pick was dropped at 0.13b.
  That commit is not in the pinned Triton history, the tree has no `ast.Num`,
  and the masked `|| true` cherry-pick had been a no-op.

## TorchAO

- [Honor `PYTORCH_ROCM_ARCH` instead of hard-coding `gfx942`](../packages/python-torchao-rocm-gfx1151/0001-setup.py-honor-pytorch-rocm-arch.patch)
  - Makes the upstream ROCm build use an explicit environment-selected target
    arch so the local package can build for `gfx1151`.
- [Include `<format>` before the HIP runtime in `swizzle.cpp`](../packages/python-torchao-rocm-gfx1151/0003-swizzle-include-format-before-hip-runtime.patch)
  - `amdclang++` compiles `torchao/csrc/rocm/swizzle/swizzle.cpp` as plain
    C++. In that mode `hip/amd_detail/host_defines.h` defines `__noinline__`
    as an empty macro, so GCC 16 `<format>` (reached through ATen's
    `<chrono>`) turns `[[__gnu__::__noinline__]]` into `[[__gnu__::]]` and
    fails with `expected identifier`. Parsing `<format>` first keeps the
    attribute intact. HIP bug:
    https://github.com/ROCm/rocm-systems/issues/9897. Upstream TorchAO
    removed `swizzle.cpp` on `main` in
    https://github.com/pytorch/ao/pull/4697 (commit `ac1a803c60`, after
    `v0.18.0`). Drop the patch at the first packaged TorchAO release without
    `swizzle.cpp`, or once the packaged HIP headers stop defining
    `__noinline__` in plain C++ mode.

## Torch-MIGraphX

- [Keep Dynamo registration lazy](../packages/python-torch-migraphx-gfx1151/0002-keep-dynamo-registration-lazy.patch)
  - Keeps base import and the FX lowering path usable while Dynamo backend
    registration remains opt-in on this Python 3.14 and PyTorch 2.12 stack.
- [Relax numpy runtime metadata cap](../packages/python-torch-migraphx-gfx1151/0003-relax-numpy-runtime-cap.patch)
  - Matches the wheel metadata to the repo's NumPy 2.x lane after host FX
    lowering validation.
- [Preload AOTAutograd before MIGraphX native modules](../packages/python-torch-migraphx-gfx1151/0004-preload-aot-autograd-before-native-extension.patch)
  - Avoids the local import-order crash and lets
    `torch.compile(..., backend="migraphx")` register the named backend.

## Patch Hygiene

- Keep patches narrowly scoped when they may plausibly be reused downstream or
  proposed upstream.
- Merge patches when follow-on fixes are inseparable parts of one behavioral
  change.
- Convert lingering scripted source mutations into package-local patch files
  once the behavior is understood and expected to persist.
