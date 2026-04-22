# Notable Original Patches

This repo keeps source changes as patch files when the change is expected to
persist, deserves independent review, or may be useful outside this exact
system.

This file is a curated summary of notable accepted original patches, not an
exhaustive applied-patch inventory. For the complete package patch list, start
from `policies/recipe-packages.toml`, `packages/*/recipe.json`, and generated
`packages/*/PKGBUILD` patch application blocks. Runtime-sensitive local-origin
patches and expected-failure findings that were quarantined after the
2026-04-20 self-hosted rebuild confidence boundary are recorded in
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
- [ROCm padded EAGLE/MTP drafter count typing](../packages/python-vllm-rocm-gfx1151/0012-rocm-keep-eagle-padded-drafter-count-int32.patch)
  - Keeps `eagle_prepare_next_token_padded_kernel` compiling on ROCm/Triton by
    forcing `valid_count` to `int32` in both Triton branches.
  - Covers the Qwen MTP server failure where the padded drafter batch path
    rejected the branch merge with mismatched `uint32` and `int1` scalar types.
- [DFlash speculators config parsing](../packages/python-vllm-rocm-gfx1151/0013-speculators-dflash-config-parsing.patch)
  - Backports the narrow `speculators` parser addition from vLLM PR #38300 so
    DFlash speculators-format configs map to `DFlashDraftModel`.
  - This is not full DFlash runtime support; upstream `qwen3_dflash.py`, DFlash
    proposer/runtime code, and registry integration remain separate follow-up
    work before the blocked DFlash scenario can be promoted.
- Runtime-sensitive vLLM carries that needed post-rebuild confirmation are
  recorded in
  [the rebuild revalidation ledger](maintainers/rebuild-revalidation.md).

## AITER

- [gfx1x fused-MoE experiment compatibility](../packages/python-amd-aiter-gfx1151/0003-fused-moe-unknown-gfx-falls-back-to-2stage.patch)
  - Keeps unknown gfx targets from keying directly into missing 1-stage fused
    MoE metadata and lets them fall back to the 2-stage path.
- [Missing 1-stage ASM metadata skip](../packages/python-amd-aiter-gfx1151/0004-moe-tuner-skips-missing-1stage-asm-metadata.patch)
  - Lets the MoE tuner skip unavailable 1-stage ASM metadata instead of
    treating it as a hard failure.
- [CK MoE splitk normalization and forwarding](../packages/python-amd-aiter-gfx1151/0005-ck-moe-normalizes-zero-splitk-and-forwards-stage2.patch)
  - Normalizes `splitk` values of `None` or `0` to `1` and forwards the chosen
    value through the CK 2-stage path.
  - These patches are retained for explicit AITER fused-MoE experiments, not as
    evidence that the maintained Gemma 4 lane should leave Triton unquantized
    MoE.

## TorchAO

- [Honor `PYTORCH_ROCM_ARCH` instead of hard-coding `gfx942`](../packages/python-torchao-rocm-gfx1151/0001-setup.py-honor-pytorch-rocm-arch.patch)
  - Makes the upstream ROCm build use an explicit environment-selected target
    arch so the local package can build for `gfx1151` instead of compiling only
    for MI300-class `gfx942`.
- [Python 3.14 PT2E union aliases](../packages/python-torchao-rocm-gfx1151/0002-python-3.14-pt2e-union-aliases.patch)
  - Keeps `torchao.quantization.pt2e` importable on Python 3.14 by guarding
    `__module__` assignment on `typing.Union` aliases that no longer accept it.

## Torch-MIGraphX

- [Import migrated PT2E quantization from TorchAO](../packages/python-torch-migraphx-gfx1151/0001-import-pt2e-quantization-from-torchao.patch)
  - Lets Torch-MIGraphX populate `torch.ops.quantized_decomposed` on the local
    PyTorch 2.11 stack, where PT2E quantization lives under TorchAO.
- [Keep Dynamo registration lazy](../packages/python-torch-migraphx-gfx1151/0002-keep-dynamo-registration-lazy.patch)
  - Keeps base import and the FX lowering path usable while Dynamo backend
    registration still segfaults after loading `_torch_migraphx` on this Python
    3.14 and PyTorch 2.11 stack.
- [Relax numpy runtime metadata cap](../packages/python-torch-migraphx-gfx1151/0003-relax-numpy-runtime-cap.patch)
  - Matches the wheel metadata to the repo's numpy 2.x lane after host FX
    lowering validation with `python-numpy-gfx1151`.

## Patch Hygiene

- Keep patches narrowly scoped when they may plausibly be reused in another
  downstream or proposed upstream.
- Merge patches when several follow-on fixes are inseparable parts of one
  behavioral change.
- Convert lingering scripted source mutations into package-local patch files
  once the behavior is understood and expected to persist.
