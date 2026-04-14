# Current State

Status as of 2026-04-13.

## Live Host State

The first full live cutover completed successfully on the reference Arch host.

Installed and validated at least once on the live host:

- generated TheRock/ROCm split package family
- AOCL layer
- optimized `python-gfx1151`
- rebuilt wheel layer
- Triton and AOTriton
- PyTorch, TorchVision, AITER, and vLLM
- `llama.cpp` HIP and Vulkan backends
- Lemonade server/app/meta packages

## Live Smoke Coverage

The following smoke checks have already passed on the reference host:

- `rocminfo`
- `hipcc --version`
- `amdclang --version`
- `python -c 'import torch; ...'`
- `python -c 'import vllm; ...'`
- `llama-cli-hip-gfx1151 --help`
- `llama-cli-vulkan-gfx1151 --help`
- `lemonade --help`
- `lemond --help`

## Important Package Decisions

- `python-gfx1151` is rebased onto Arch/Cachy Python `3.14.4`, not the
  recipe's older Python `3.13.x` pin.
- `python-pytorch-opt-rocm-gfx1151` tracks `ROCm/pytorch` `release/2.11`,
  pinned to commit `0446f7ba2fd`, with package version aligned to the built
  wheel version.
- `python-openai-harmony-gfx1151` is now the local closure package for vLLM's
  GPT-OSS/Harmony path, using `aur/python-openai-harmony` as the baseline but
  carrying upstream's missing `python-pydantic` runtime dependency.
- `python-vllm-rocm-gfx1151` uses upstream `v0.19.0` tarball plus the local
  Python-3.14 compatibility delta and now depends on the local
  `python-openai-harmony-gfx1151` package for Harmony runtime closure.
- `python-vllm-rocm-gfx1151` also carries a ROCm-specific compatibility gate
  for the vendored `triton_kernels` tree, so the `gfx1151` lane falls back
  cleanly when the installed Triton runtime lacks CUDA-only APIs such as
  `triton.language.target_info`.
- `llama.cpp-hip-gfx1151` uses `aur/llama.cpp-hip` as the authoritative
  baseline reference.
- `llama.cpp-vulkan-gfx1151` currently uses `aur/llama.cpp-vulkan-bin` as the
  closest backend-specific reference until a maintained source-build Vulkan
  package exists.
- Lemonade is intentionally customized so:
  - `llamacpp:rocm` and `llamacpp:vulkan` are packaged system-managed backends
  - `llamacpp:cpu` remains Lemonade-managed and downloadable
  - `llamacpp:system` is removed from this custom variant
  - the backend table identifies the packaged backends explicitly as:
    - `System llama-server-hip-gfx1151 llama.cpp b8611`
    - `System llama-server-vulkan-gfx1151 llama.cpp b8611`

## Known Deferred Follow-up Work

- `python-flydsl-gfx1151`
  - blocked on the current `rocm-llvm-gfx1151` MLIR development surface being
    insufficient for downstream FlyDSL packaging
- package hygiene
  - remove remaining embedded build-path leakage where still present
  - convert remaining scripted source edits into durable patch files where
    practical
- vLLM runtime follow-up
  - decide whether the host `torchao` extension failure is harmless warning
    noise or needs package-level remediation on this lane
- TorchVision cleanup
  - rebuild cleanly without the temporary build-only ROCm soname shim
- Lemonade presentation polish
  - keep the backend table explicit about packaged ROCm/Vulkan backends after
    each relevant package rebuild
- benchmarking
  - benchmark this stack against `aur/rocm-gfx1151-bin`
  - revisit whether every maintained local optimization still earns its cost

## Repository Status

This repo is now the canonical source for:

- package definitions
- package policy
- local patch carry
- maintainer documentation
- the local pacman repo workflow

Older draft packaging trees and migration leftovers are historical inputs, not
authoritative sources.
