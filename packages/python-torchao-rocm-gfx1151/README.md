# python-torchao-rocm-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `python-project-torchao`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/pytorch/ao`
- Package version: `0.18.0`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-pytorch-opt-rocm, extra/python-pytorch-rocm`
- Authoritative reference package: `none`
- Advisory reference packages: `extra/python-pytorch-opt-rocm, extra/python-pytorch-rocm`
- Applied source patch files/actions: `2`

## Recipe notes

Builds TorchAO `0.18.0` from the upstream git tag. The package keeps the git
source lane that `0.17.0` needed because that release published no sdist on
PyPI. TorchAO `0.18.0` supports `torch 2.11.0+`, and this package builds it
against `python-pytorch-opt-rocm-gfx1151 2.12.0`.

TorchAO `0.18.0` guards the `typing.Union` `__module__` writes in
`torchao.quantization.pt2e` with `sys.version_info < (3, 14)`, so the local
Python 3.14 PT2E patch that `0.17.0` needed is retired. The release also
removes the v1 `AffineQuantizedTensor` and layout stack.

TorchAO imports `torch` at build time and still hard-codes `gfx942` for ROCm
extension builds. The local package exports `VERSION_SUFFIX=` to keep the
wheel on the stable release version, exports `ROCM_HOME=/opt/rocm` so
PyTorch's extension helpers use the real split-layout ROCm headers, and
patches `setup.py` so the ROCm target arch follows `PYTORCH_ROCM_ARCH`.

`0003-swizzle-include-format-before-hip-runtime.patch` makes `torchao/csrc/rocm/swizzle/swizzle.cpp` include
`<format>` before `<hip/hip_runtime.h>`. `amdclang++` compiles that file as
plain C++, where `hip/amd_detail/host_defines.h` defines `__noinline__` as an
empty macro. GCC 16 `<format>`, which ATen reaches through `<chrono>`, spells
`[[__gnu__::__noinline__]]`; after the macro runs, clang rejects the attribute
with `expected identifier`. The HIP bug is
https://github.com/ROCm/rocm-systems/issues/9897. Upstream TorchAO removed
`swizzle.cpp` on `main` in https://github.com/pytorch/ao/pull/4697 (after
`v0.18.0`), so drop the patch at the first TorchAO release without that file,
or earlier if the packaged HIP headers stop defining `__noinline__` in plain
C++ mode.

The staged package was verified locally with:
- `readelf -d` showing `RUNPATH [$ORIGIN:$ORIGIN/../torch/lib:/opt/rocm/lib]`
- `ldd -r` resolving cleanly against `/usr/lib/python3.14/site-packages/torch/lib`
- `PYTHONPATH=<pkgdir>/site-packages python -c 'import torchao'` succeeding

The reference host has now validated the installed package with a clean
`import torchao` path, the tiny serialized-checkpoint
`tools/torchao_vllm_smoke.py` round trip, and the tracked
`vllm.gemma4.e2b.torchao.online-real-model` scenario. The Gemma 4 online path
loaded `google/gemma-4-E2B-it` with vLLM `quantization=torchao`, selected
`ROCM_AITER_UNIFIED_ATTN`, and generated successfully.

The serialized Gemma 4 real-model path now writes processor files correctly,
but remains blocked during vLLM weight loading by TorchAO tensor metadata:
`AttributeError: 'Tensor' object has no attribute 'tensor_data_names'`.

The `Stored version is not the same as current default version` warning was
expected with TorchAO `0.17.0` when using `Int8WeightOnlyConfig(version=2)`.
TorchAO `0.18.0` makes version 2 the default and removes version 1, so recheck
whether the warning still appears after the rebuild. Version 2 is still the
one the serialized safetensors path requires. The ROCm
custom paged-attention fallback warning is vLLM shape-gated and did not appear
in the Gemma 4 online TorchAO run.


## Scaffold notes

- This package follows the repo's native wheel lane but needs two TorchAO-specific corrections: export VERSION_SUFFIX= so the wheel advertises a real release version, and patch the installed _C extension RPATH to include the sibling torch/lib directory.
- TorchAO 0.17.0 published no sdist on PyPI, so the local source-build lane follows the upstream git tag and initializes the pinned cutlass submodule in prepare().
- The upstream 0.18.0 setup.py still hard-codes --offload-arch=gfx942 on ROCm, so keep the local source patch that makes the ROCm target arch configurable via PYTORCH_ROCM_ARCH.
- The local build must also export ROCM_HOME=/opt/rocm. On this host, hipcc is visible under /usr/bin, but the actual HIP headers live under /opt/rocm/include; without the explicit prefix, PyTorch's extension helper falls back to ROCM_HOME=/usr and the build dies on hip/hip_runtime.h.

## Intentional Divergences

- There is no standalone TorchAO package in Arch-family repositories, so this package is closure-first and tracks the upstream TorchAO compatibility matrix against the local PyTorch ROCm lane.
- Carries a package-local ROCm patch so the source build honors PYTORCH_ROCM_ARCH instead of hard-coding gfx942, exports ROCM_HOME=/opt/rocm so PyTorch picks up the real split-layout HIP headers, and carries a post-install RPATH fix so the optional _C extension can resolve torch/lib at runtime.
- Carries 0003-swizzle-include-format-before-hip-runtime.patch so the plain-C++ ROCm swizzle TU parses libstdc++ <format> before HIP's host-mode empty __noinline__ macro can corrupt GCC 16's [[__gnu__::__noinline__]] attribute.

## Update Notes

- Check the upstream TorchAO compatibility table first during updates; this package must stay on the release line built for the local PyTorch lane rather than a nearby +git snapshot.
- Keep VERSION_SUFFIX empty for release builds unless upstream changes its versioning model; +git local versions bypass TorchAO's own compatibility gate and recreate avoidable import-time warnings.
- Keep ROCM_HOME=/opt/rocm in the build environment unless the local ROCm packaging layout changes. The host-visible hipcc wrapper may live under /usr/bin, but the headers and shared libraries still come from /opt/rocm.
- Re-verify the installed extension with readelf -d and ldd -r after each update. A clean package needs both a usable torch/lib runpath and zero unresolved ATen/Torch symbols once torch/lib is visible.
- Keep the repo-local tools/torchao_vllm_smoke.py helper passing for both the tiny serialized checkpoint and the Gemma 4 online quantization path. Treat the serialized Gemma 4 real-model checkpoint path as blocked until the TorchAO/vLLM tensor metadata mismatch is fixed.
- Keep -famd-opt out of TorchAO wheel CFLAGS/CXXFLAGS while retaining it in LDFLAGS as a clang driver link flag; do not move it back into the wheel compile flags without a fresh TorchAO extension build failure that requires it there.
- On 2026-05-26, bump pkgrel to 4 for delivery of the TorchAO extension rebuild against python-pytorch-opt-rocm-gfx1151 2.12.0-2 from ROCm/pytorch release/2.12 commit 26872debb4452ea6dc898288618a15595e2317d9.
- On 2026-06-15, bump pkgrel to 6 for the c7badbdf runtime-base rebuild so TorchAO supersedes the unmerged ab32a1f/pkgrel-5 host-drift artifact.
- On 2026-09-25, update to TorchAO 0.18.0 (tag v0.18.0, commit 5f2baf9d575cf732362594c998c399902942531f) for the rebuild against python-pytorch-opt-rocm-gfx1151 2.12.0-5. Patch 0001 applies with a 10-line offset. Patch 0002 is dropped because 0.18.0 guards the typing.Union __module__ writes with sys.version_info < (3, 14). 0.18.0 raises the minimum PyTorch to 2.11 and removes the v1 AffineQuantizedTensor and layout stack; Int8WeightOnlyConfig version 1 is gone, and version 2 is the default. Recheck the vLLM TorchAO scenarios and tools/torchao_vllm_smoke.py after the rebuild.
- On 2026-09-25, add 0003-swizzle-include-format-before-hip-runtime.patch after the first 0.18.0-1 build failed in torchao/csrc/rocm/swizzle/swizzle.cpp with 'expected identifier' at GCC 16 <format> [[__gnu__::__noinline__]]; pkgrel stays 1 because no 0.18.0-1 artifact was built or published. Drop the patch when the packaged TorchAO release no longer ships swizzle.cpp (upstream removed it on main in https://github.com/pytorch/ao/pull/4697, commit ac1a803c60, after v0.18.0) or when the packaged HIP headers stop defining __noinline__ in plain C++ mode (https://github.com/ROCm/rocm-systems/issues/9897).

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
