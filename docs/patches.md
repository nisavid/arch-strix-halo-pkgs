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

## vLLM

- [Python 3.14 compatibility on the packaged stable lane](../packages/python-vllm-rocm-gfx1151/0001-python-3.14-version-gates.patch)
  - Extends the packaged `v0.19.0` lane to accept Python `3.14` by relaxing
    the Python upper bound and extending the hard-coded CMake version gate.
  - This is a packaging-facing compatibility patch, not a Strix Halo–specific
    optimization, so it is the clearest current upstreaming candidate in the
    repo.

## AITER

- [RDNA 3.5 header compatibility for `gfx1151`](../packages/python-amd-aiter-gfx1151/0001-gfx1151-rdna35-header-compat.patch)
  - Converts the current `gfx1151` include-tree fixes into a package-local
    source patch instead of post-install file replacement.
  - Adds RDNA-safe fallbacks for packed FP8 and reduction paths that assume
    CDNA-only instructions.

## Patch Hygiene

- Keep patches narrowly scoped when they may plausibly be reused in another
  downstream or proposed upstream.
- Merge patches when several follow-on fixes are inseparable parts of one
  behavioral change.
- Convert lingering scripted source mutations into package-local patch files
  once the behavior is understood and expected to persist.
