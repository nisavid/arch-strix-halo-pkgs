# Patch Inventory

This page explains the source changes that are important enough to call out by
name. It is a curated map, not the complete patch list.

For the complete applied-patch inventory, inspect:

- `policies/recipe-packages.toml`
- `packages/*/recipe.json`
- `packages/*/PKGBUILD`
- patch files beside the affected package

Runtime-sensitive local-origin patches and expected-failure findings from the
post-rebuild quarantine are recorded in the
[rebuild revalidation ledger](maintainers/rebuild-revalidation.md).

## Why Patches Live Here

This repo keeps source changes as patch files when a change is expected to
persist, deserves independent review, or may be useful outside this exact host.
Inline shell edits are reserved for narrow packaging mechanics. When behavior
becomes durable, prefer a named patch that another maintainer can review.

## Lemonade

- [Linux NPU fallback when accel-device opens fail](../packages/lemonade-server/0001-linux-npu-fallback-to-pci-id-when-accel-open-fails.patch)
  - Falls back to PCI identification when `/dev/accel/*` probing fails even
    though the hardware is still identifiable from sysfs.
- [Treat packaged HIP and Vulkan `llama.cpp` backends as system-managed](../packages/lemonade-server/0002-llamacpp-external-backends-are-system-managed.patch)
  - Makes Lemonade treat the packaged ROCm and Vulkan `llama.cpp` backends as
    system-managed backends rather than downloadable runtimes.
  - Includes the config-load, backend-table, and CLI presentation changes that
    keep the override visible after the first startup.
- [Remove the generic `llamacpp:system` backend](../packages/lemonade-server/0003-remove-llamacpp-system-backend.patch)
  - Keeps this custom build focused on the explicit HIP and Vulkan lanes this
    repo packages.
- [Override system-managed `llama.cpp` metadata for packaged backends](../packages/lemonade-server/0004-system-managed-llamacpp-metadata.patch)
  - Makes the Lemonade GUI and backend API report the packaged `llama.cpp`
    revision and upstream `ggml-org/llama.cpp` release URL for the local ROCm
    and Vulkan lanes.

## vLLM

- [Python 3.14 compatibility on the packaged stable lane](../packages/python-vllm-rocm-gfx1151/0001-python-3.14-version-gates.patch)
  - Extends the packaged `v0.19.1` lane to accept Python `3.14` by relaxing the
    Python upper bound and supported-version gate.
  - This packaging-facing compatibility patch is the clearest current
    upstreaming candidate in the repo.
- [ROCm large-head Triton unified-attention tile reduction](../packages/python-vllm-rocm-gfx1151/0005-rocm-reduce-triton-unified-attention-prefill-tile-for-large-heads.patch)
  - Keeps large-head ROCm prefill paths such as Gemma 4 global attention under
    the gfx1151 LDS/shared-memory limit.
  - Revalidated after the 2026-04-20 self-hosted rebuild with forced Triton
    attention coverage and the package-local guard.
- [ROCm padded EAGLE/MTP drafter count typing](../packages/python-vllm-rocm-gfx1151/0012-rocm-keep-eagle-padded-drafter-count-int32.patch)
  - Keeps `eagle_prepare_next_token_padded_kernel` compiling on ROCm/Triton by
    forcing `valid_count` to one scalar dtype across Triton branches.
- [DFlash speculators config parsing](../packages/python-vllm-rocm-gfx1151/0013-speculators-dflash-config-parsing.patch)
  - Backports the narrow `speculators` parser addition from vLLM PR #38300 so
    DFlash-format configs resolve to `DFlashDraftModel`.
  - This is parser support only. Full DFlash runtime/model support remains a
    separate follow-up.
- [ROCm FlashAttention Triton interface detection](../packages/python-vllm-rocm-gfx1151/0014-rocm-detect-flash-attn-triton-interface.patch)
  - Lets vLLM detect the local pure-Python `flash_attn` package, which exposes
    AITER's Triton AMD backend through `flash_attn.flash_attn_interface`.
- [ROCm FlashAttention CK interface gate](../packages/python-vllm-rocm-gfx1151/0015-rocm-gate-flash-attn-ck-interface.patch)
  - Keeps forced CK/direct FlashAttention paths explicit so vLLM only promotes
    the local CK backend when the imported surface and kernel behavior match
    the engine route being tested.
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

## TorchAO

- [Honor `PYTORCH_ROCM_ARCH` instead of hard-coding `gfx942`](../packages/python-torchao-rocm-gfx1151/0001-setup.py-honor-pytorch-rocm-arch.patch)
  - Makes the upstream ROCm build use an explicit environment-selected target
    arch so the local package can build for `gfx1151`.
- [Python 3.14 PT2E union aliases](../packages/python-torchao-rocm-gfx1151/0002-python-3.14-pt2e-union-aliases.patch)
  - Keeps `torchao.quantization.pt2e` importable on Python 3.14 by guarding
    `typing.Union` alias metadata writes.

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
