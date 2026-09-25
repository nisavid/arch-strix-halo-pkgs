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

## CPython

- [Build Python with POSIX 2024](../packages/python-gfx1151/0001-build-python-with-posix-2024.patch)
  - A verbatim copy of upstream cpython `927eb448` (gh-144309). It raises the
    configure feature macros from POSIX 2008 to POSIX 2024.
  - Carried for parity with Arch `core/python` 3.14.7-1, the authoritative
    reference, which applies the same commit. Drop it once a CPython 3.14
    release contains the commit or Arch stops carrying it.

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

- [ROCm local carry refreshed for vLLM 0.20.0](../packages/python-vllm-rocm-gfx1151/0016-rocm-refresh-local-carry-for-vllm-0.20.0.patch)
  - Consolidates the package-local ROCm, Gemma, Qwen, TorchAO, CLI laziness,
    sampler, EAGLE/MTP, and FlashAttention interface carry on top of upstream
    vLLM 0.20.0.
  - Keeps large-head ROCm prefill paths such as Gemma 4 global attention under
    the gfx1151 LDS/shared-memory limit.
  - Keeps Qwen speculative decoding compiling on ROCm/Triton by forcing the
    padded drafter batch `valid_count` path to one scalar dtype across Triton
    branches.
  - Lets vLLM detect the packaged pure-Python `flash_attn` interface that
    exposes AITER's Triton AMD backend, while keeping CK/direct FlashAttention
    promotion behind the imported paged-KV surface and kernel behavior needed
    by the vLLM engine route.
  - Uses upstream vLLM 0.20.0 Python 3.14 metadata and DFlash support instead
    of retaining the former local Python-version and narrow DFlash parser
    backport patches.
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

## PyTorch

- [Initialize NumPy before ROCm global dependencies](../packages/python-pytorch-opt-rocm-gfx1151/0007-initialize-numpy-before-global-deps.patch)
  - Loads NumPy's OpenBLAS provider before PyTorch loads ROCm global
    dependencies, keeping `import torch` stable on the installed TheRock 7.13
    runtime stack.

## Triton

- [Python 3.14 and pybind11 build-system compatibility](../packages/python-triton-gfx1151/0001-python-3.14-and-pybind11-build-system.patch)
  - Keeps the ROCm Triton fork on the repo's Python 3.14 lane while using the
    Arch-provided build tools from the package metadata.
- [Disable `-Werror` with TheRock LLVM headers](../packages/python-triton-gfx1151/0002-disable-werror-with-therock-llvm-headers.patch)
  - Prevents warning-only differences in the local LLVM/header lane from
    failing the package build.
- [Add `AttrsDescriptor.__repr__` for Inductor codegen](../packages/python-triton-gfx1151/0003-attrs-descriptor-repr-for-inductor.patch)
  - Keeps `torch.compile` / Inductor-generated Python valid when it serializes
    Triton metadata with `repr()`.

## TorchAO

- [Honor `PYTORCH_ROCM_ARCH` instead of hard-coding `gfx942`](../packages/python-torchao-rocm-gfx1151/0001-setup.py-honor-pytorch-rocm-arch.patch)
  - Makes the upstream ROCm build use an explicit environment-selected target
    arch so the local package can build for `gfx1151`.
- [Python 3.14 PT2E union aliases](../packages/python-torchao-rocm-gfx1151/0002-python-3.14-pt2e-union-aliases.patch)
  - Keeps `torchao.quantization.pt2e` importable on Python 3.14 by guarding
    `typing.Union` alias metadata writes.

## MIGraphX (TheRock stage)

- No-MLIR build stubs, applied inline by
  [`tools/stage_migraphx_for_therock.zsh`](../tools/stage_migraphx_for_therock.zsh)
  - AMDMIGraphX 2.16.1 (`2487b688`) still exports `dump_mlir_to_file`,
    `is_module_fusible`, `adjust_param_shapes`, and `dump_mlir_to_mxr` from
    `mlir.hpp` without defining them in the `MIGRAPHX_MLIR`-off branch of
    `src/targets/gpu/mlir.cpp`. The stubs let the repo build MIGraphX with
    rocMLIR disabled.
  - The former `RockEnums.h` include guard is no longer carried: upstream #4962
    moved that include inside `#ifdef MIGRAPHX_MLIR` before 2.16.
- `rocm_add_version_resource` configure shim, written by the same script and
  passed as `CMAKE_PROJECT_INCLUDE`
  - AMDMIGraphX 2.16.1 calls `rocm_add_version_resource` for each library and
    tool. Its pinned rocm-cmake (`1d4652ae`) defines it, but the rocm-cmake
    0.14.0 that TheRock 7.14.1 ships does not, so configure fails against the
    stage. Upstream only writes a Windows `.rc` version resource under
    `if(WIN32)`, so the shim defines a no-op. The script adds it only when the
    staged rocm-cmake modules lack the function; drop it once the TheRock
    payload carries a rocm-cmake that defines it.

## Torch-MIGraphX

- [Import migrated PT2E quantization from TorchAO](../packages/python-torch-migraphx-gfx1151/0001-import-pt2e-quantization-from-torchao.patch)
  - Lets Torch-MIGraphX populate `torch.ops.quantized_decomposed` on the local
    PyTorch 2.11 stack, where PT2E quantization lives under TorchAO.
- [Keep Dynamo registration lazy](../packages/python-torch-migraphx-gfx1151/0002-keep-dynamo-registration-lazy.patch)
  - Keeps base import and the FX lowering path usable while Dynamo backend
    registration remains opt-in on this Python 3.14 and PyTorch 2.11 stack.
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
