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
- `python -c 'import amdsmi; ...'`
- `llama-cli-hip-gfx1151 --help`
- `llama-cli-vulkan-gfx1151 --help`
- `lemonade --help`
- `lemond --help`

## Important Package Decisions

- `python-gfx1151` is rebased onto Arch/Cachy Python `3.14.4`, not the
  recipe's older Python `3.13.x` pin.
- `amdsmi-gfx1151` now installs an `amd_smi.pth` import hook into Python
  `site-packages`, so Python `3.14` can import the ROCm-shipped `amdsmi`
  module from `/opt/rocm/share/amd_smi` without extra `PYTHONPATH` glue on the
  host.
- `python-pytorch-opt-rocm-gfx1151` tracks `ROCm/pytorch` `release/2.11`,
  pinned to commit `0446f7ba2fd`, with package version aligned to the built
  wheel version.
- `python-torchvision-rocm-gfx1151` now rebuilds cleanly against the paired
  PyTorch lane without the earlier build-only `librocsolver.so.0` shim; if
  that workaround ever becomes necessary again, treat it as a PyTorch/runtime
  regression rather than reintroducing the shim in TorchVision.
- `python-torchvision-rocm-gfx1151` also now sanitizes embedded HIP source
  paths correctly: the rebuilt `_C.so` no longer leaks repo-local `$srcdir`
  paths and instead points at `/usr/src/debug/python-torchvision-rocm-gfx1151`.
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
- `python-vllm-rocm-gfx1151` also now carries two small host-facing runtime
  compatibility fixes:
  - the ROCm GCN-arch fallback no longer crashes in an import-time
    `warning_once` circular path when `amdsmi` cannot return ASIC info and
    vLLM falls back to `torch.cuda`
  - SageMaker-specific API routers now treat
    `model_hosting_container_standards` as optional, so base CLI and API usage
    no longer hard-fail on that extra package being absent
- The host `python-torchao-rocm` package currently fails to load its optional
  `_C.abi3.so` extension because the shipped binary is not import-clean
  against the installed PyTorch runtime. For the current vLLM lane this is
  treated as harmless warning noise: `import vllm` is clean, and the TorchAO
  Python-level APIs vLLM actually touches (`config_from_dict`, `quantize_`,
  and packed-tensor conversion) still work on the reference host.
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
  - remove remaining embedded build-path leakage where still present in
    PyTorch and vLLM
  - convert remaining scripted source edits into durable patch files where
    practical
- vLLM build-path follow-up
  - a trial patch that taught `setup.py` to `shlex.split()` quoted
    `CMAKE_ARGS` and injected `CMAKE_HIP_FLAGS` did route source-prefix maps
    into the HIP compile lane, but it also made both vLLM build attempts fail
    in `csrc/sampler.hip` on gfx1151 with:
    `Invalid dpp_ctrl value: wavefront shifts are not supported on GFX10+`
  - treat that as the current blocker before attempting any further vLLM
    build-path sanitization
- vLLM/TorchAO follow-up
  - only revisit the external `python-torchao-rocm` package if this repo needs
    working TorchAO custom ops or `--quantization torchao` paths that truly
    depend on the native `_C` extension rather than the Python-level APIs
- vLLM/Gemma follow-up
  - after the current `amdsmi` and optional-SageMaker fixes land on the host,
    rerun the Gemma 4 safetensors smoke test and record whether any remaining
    blocker is a real model-load/runtime issue rather than platform detection
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
