# Notable Original Patches

This repo keeps source changes as patch files when the change is expected to
persist, deserves independent review, or may be useful outside this exact
system.

This file is a curated summary of notable accepted original patches, not an
exhaustive applied-patch inventory. For the complete package patch list, start
from `policies/recipe-packages.toml`, `packages/*/recipe.json`, and generated
`packages/*/PKGBUILD` patch application blocks. Runtime-sensitive local-origin
patches and expected-failure findings that still need confirmation after the
2026-04-20 self-hosted rebuild confidence boundary live in
[the rebuild revalidation ledger](maintainers/rebuild-revalidation.md).

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
  - Extends the packaged `v0.19.1` lane to accept Python `3.14` by relaxing
    the Python upper bound and extending the hard-coded CMake version gate.
  - This is a packaging-facing compatibility patch, not a Strix Halo–specific
    optimization, so it is the clearest current upstreaming candidate in the
    repo.
- [ROCm large-head Triton unified-attention tile reduction](../packages/python-vllm-rocm-gfx1151/0005-rocm-reduce-triton-unified-attention-prefill-tile-for-large-heads.patch)
  - Keeps large-head ROCm prefill paths such as Gemma 4 global attention under
    the gfx1151 LDS/shared-memory limit by reducing the Triton unified-attention
    prefill tile to `16` when `head_size >= 512`.
  - Revalidated after the 2026-04-20 self-hosted rebuild with the forced
    `TRITON_ATTN` Gemma 4 E2B server scenario and the package-local tile-size
    guard.
- Provisional runtime-sensitive vLLM carries are tracked in
  [the rebuild revalidation ledger](maintainers/rebuild-revalidation.md) until
  post-rebuild scenario evidence promotes or retires them.

## AITER

- Provisional runtime-sensitive AITER carries are tracked in
  [the rebuild revalidation ledger](maintainers/rebuild-revalidation.md) until
  post-rebuild build and scenario evidence promotes or retires them.

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
