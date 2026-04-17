# Notable Original Patches

This repo keeps source changes as patch files when the change is expected to
persist, deserves independent review, or may be useful outside this exact
system.

## Lemonade

- [Linux NPU fallback when accel-device opens fail](../packages/lemonade-server/0001-linux-npu-fallback-to-pci-id-when-accel-open-fails.patch)
  - Falls back to PCI identification when `/dev/accel/*` probing fails even
    though the hardware is still clearly identifiable from sysfs.
- [Treat packaged HIP and Vulkan `llama.cpp` backends as system-managed](../packages/lemonade-server/0002-llamacpp-external-backends-are-system-managed.patch)
  - Makes Lemonade treat the packaged ROCm and Vulkan `llama.cpp` backends as
    system-managed backends rather than downloadable runtimes.
  - Includes the config-load, backend-table, and CLI presentation changes
    needed to make that behavior actually hold after the first startup.
- [Remove the generic `llamacpp:system` backend](../packages/lemonade-server/0003-remove-llamacpp-system-backend.patch)
  - Keeps this custom build focused on the explicit HIP and Vulkan lanes that
    this repo actually packages.
- [Override system-managed `llama.cpp` metadata for packaged backends](../packages/lemonade-server/0004-system-managed-llamacpp-metadata.patch)
  - Makes the Lemonade GUI and backend API report the packaged `llama.cpp`
    revision and the upstream `ggml-org/llama.cpp` release URL for the
    system-managed ROCm and Vulkan lanes instead of Lemonade's downloader
    defaults.

## vLLM

- [Python 3.14 compatibility on the packaged stable lane](../packages/python-vllm-rocm-gfx1151/0001-python-3.14-version-gates.patch)
  - Extends the packaged `v0.19.0` lane to accept Python `3.14` by relaxing
    the Python upper bound and extending the hard-coded CMake version gate.
  - This is a packaging-facing compatibility patch, not a Strix Halo–specific
    optimization, so it is the clearest current upstreaming candidate in the
    repo.
- [Keep `vllm --version` on a metadata-only path](../packages/python-vllm-rocm-gfx1151/0002-cli-version-avoids-eager-runtime-imports.patch)
  - Removes eager benchmark imports from `vllm.entrypoints.cli.__init__` and
    short-circuits `--version` before the CLI reaches optional OpenAI and
    Triton runtime modules.
  - This keeps the version smoke test useful on the packaged ROCm lane even
    when unrelated optional runtime deps are absent or intentionally patched.
- [Gate vendored Triton kernels on ROCm runtime support](../packages/python-vllm-rocm-gfx1151/0003-rocm-gate-vendored-triton-kernels-on-runtime-support.patch)
  - Treats vLLM's vendored `triton_kernels` tree as unavailable when the
    installed Triton runtime lacks CUDA-only APIs such as
    `triton.language.target_info` or `triton.constexpr_function`.
  - This keeps the ROCm `gfx1151` lane on a clean fallback path instead of
    surfacing import-time failures from vendored CDNA/CUDA-oriented kernels.
- [Keep ROCm fallback and SageMaker routes import-safe on the packaged lane](../packages/python-vllm-rocm-gfx1151/0004-rocm-fallback-and-optional-sagemaker-standards.patch)
  - Makes the ROCm GCN-arch fallback use normal logging instead of
    `warning_once`, avoiding the import-time circular path that showed up when
    `amdsmi` could not provide ASIC info on the reference host.
  - Treats `model_hosting_container_standards` as optional for the packaged
    SageMaker and runtime-LoRA API routers, so `vllm --help` and other
    non-SageMaker entrypoints no longer fail just because that extra package is
    absent.
- [Enable gfx1x AITER and prefer it for Gemma 4 heterogeneous-head attention](../packages/python-vllm-rocm-gfx1151/0007-rocm-enable-gfx1x-aiter-and-prefer-it-for-gemma4.patch)
  - Extends ROCm AITER discovery to gfx1x and lets Gemma 4 prefer
    `ROCM_AITER_UNIFIED_ATTN` instead of the Triton unified-attention backend
    that miscompiled on gfx1151 decode.
- [Pad Gemma 4 26B-A4B MoE intermediates for ROCm AITER alignment](../packages/python-vllm-rocm-gfx1151/0010-rocm-pad-gemma4-moe-intermediate-for-aiter.patch)
  - Pads the unquantized Gemma 4 MoE intermediate size to a multiple of 128
    before vLLM shuffles expert weights into AITER runtime layout.
  - Keeps `google/gemma-4-26B-A4B-it` on the intended AITER fused-MoE path for
    the 704-wide expert shape instead of relying on a later fallback after the
    weights have already been converted.
- [Default fused-MoE to AITER on supported ROCm systems](../packages/python-vllm-rocm-gfx1151/0011-rocm-default-fused-moe-to-aiter-on-supported-systems.patch)
  - Keeps explicit environment overrides authoritative, but otherwise leaves
    supported ROCm installs on the intended fused-MoE AITER path without
    requiring a manual `VLLM_ROCM_USE_AITER=1` export.

## AITER

- [RDNA 3.5 packed-op fallback compatibility for `gfx1151`](../packages/python-amd-aiter-gfx1151/0001-gfx1151-rdna35-header-compat.patch)
  - Converts the `vec_convert.h` packed FP32/FP8/BF8 helpers into gfx11-safe
    scalar fallbacks when CDNA-only packed instructions are unavailable.
- [RDNA 3.5 wave32/DPP compatibility for `hip_reduce.h`](../packages/python-amd-aiter-gfx1151/0006-rdna35-hip-reduce-wave32-dpp-compat.patch)
  - Reworks the reduction helpers to avoid CDNA-only row-broadcast DPP paths
    on gfx11 and to keep the wave32 assumptions explicit.
- [Find `hipcc` and user-cache JIT modules on installed systems](../packages/python-amd-aiter-gfx1151/0002-jit-runtime-finds-hipcc-and-user-jit-modules.patch)
  - Makes the installed AITER runtime resolve `/opt/rocm/bin/hipcc` without
    depending on an ambient login-shell `PATH`.
  - Lets the read-only site-packages install import JIT-built modules copied
    into the writable `~/.aiter/jit/` cache instead of assuming a
    package-relative import path.
- [Unknown gfx targets fall back to the 2-stage MoE heuristics](../packages/python-amd-aiter-gfx1151/0003-fused-moe-unknown-gfx-falls-back-to-2stage.patch)
  - Avoids a `KeyError` while probing the 1-stage config table on gfx targets
    that do not ship explicit 1-stage metadata.
- [Skip missing 1-stage ASM metadata during MoE tuning](../packages/python-amd-aiter-gfx1151/0004-moe-tuner-skips-missing-1stage-asm-metadata.patch)
  - Keeps the 2-stage CK tuner usable even when the current gfx target has no
    architecture-specific 1-stage ASM metadata.
- [Normalize zero splitk and forward stage-2 splitk on CK MoE launches](../packages/python-amd-aiter-gfx1151/0005-ck-moe-normalizes-zero-splitk-and-forwards-stage2.patch)
  - Makes the AITER CK MoE wrappers treat `splitk=0` as the existing
    no-split sentinel (`1` at kernel launch) instead of passing a raw zero into
    the CK entrypoint.
  - Propagates the computed `ksplit` into stage 2 so both halves of the
    unquantized MoE path use the same launch semantics.

## TorchAO

- [Honor `PYTORCH_ROCM_ARCH` instead of hard-coding `gfx942`](../packages/python-torchao-rocm-gfx1151/0001-setup.py-honor-pytorch-rocm-arch.patch)
  - Makes the upstream ROCm build use an explicit environment-selected target
    arch so the local package can build for `gfx1151` instead of compiling only
    for MI300-class `gfx942`.

## Patch Hygiene

- Keep patches narrowly scoped when they may plausibly be reused in another
  downstream or proposed upstream.
- Merge patches when several follow-on fixes are inseparable parts of one
  behavioral change.
- Convert lingering scripted source mutations into package-local patch files
  once the behavior is understood and expected to persist.
