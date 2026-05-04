# python-torchao-rocm-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `python-project-torchao`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/pytorch/ao`
- Package version: `0.17.0`
- Recipe revision: `a1d7a68 (20260427, 16 path commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-pytorch-opt-rocm, extra/python-pytorch-rocm`
- Authoritative reference package: `none`
- Advisory reference packages: `extra/python-pytorch-opt-rocm, extra/python-pytorch-rocm`
- Applied source patch files/actions: `3`

## Recipe notes

Builds TorchAO `0.17.0` from the upstream git tag because that release does
not publish an sdist on PyPI. This release is the local TorchAO compatibility
lane for `torch 2.11.0+`.

TorchAO imports `torch` at build time and still hard-codes `gfx942` for ROCm
extension builds. The local package exports `VERSION_SUFFIX=` to keep the
wheel on the stable release version, exports `ROCM_HOME=/opt/rocm` so
PyTorch's extension helpers use the real split-layout ROCm headers, and
patches `setup.py` so the ROCm target arch follows `PYTORCH_ROCM_ARCH`.

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

The `Stored version is not the same as current default version` warning is
expected with TorchAO `0.17.0` when using `Int8WeightOnlyConfig(version=2)`;
that version is still required for the serialized safetensors path. The ROCm
custom paged-attention fallback warning is vLLM shape-gated and did not appear
in the Gemma 4 online TorchAO run.


## Scaffold notes

- This package follows the repo's native wheel lane but needs two TorchAO-specific corrections: export VERSION_SUFFIX= so the wheel advertises a real release version, and patch the installed _C extension RPATH to include the sibling torch/lib directory.
- TorchAO 0.17.0 does not publish an sdist on PyPI, so the local source-build lane follows the upstream git tag and lets setup.py initialize the pinned cutlass submodule as needed.
- The upstream 0.17.0 setup.py still hard-codes --offload-arch=gfx942 on ROCm, so keep the local source patch that makes the ROCm target arch configurable via PYTORCH_ROCM_ARCH.
- The local build must also export ROCM_HOME=/opt/rocm. On this host, hipcc is visible under /usr/bin, but the actual HIP headers live under /opt/rocm/include; without the explicit prefix, PyTorch's extension helper falls back to ROCM_HOME=/usr and the build dies on hip/hip_runtime.h.
- TorchAO 0.17.0's PT2E package assigns __module__ to typing.Union aliases. Python 3.14 rejects that assignment, so the local package carries a narrow import-compatibility patch.

## Intentional Divergences

- There is no standalone TorchAO package in Arch-family repositories, so this package is closure-first and tracks the upstream TorchAO compatibility matrix against the local PyTorch ROCm lane.
- Carries a package-local ROCm patch so the source build honors PYTORCH_ROCM_ARCH instead of hard-coding gfx942, exports ROCM_HOME=/opt/rocm so PyTorch picks up the real split-layout HIP headers, and carries a post-install RPATH fix so the optional _C extension can resolve torch/lib at runtime.
- Carries a Python 3.14 PT2E compatibility patch so torchao.quantization.pt2e can import after Python made typing.Union aliases immutable for __module__ assignment.

## Update Notes

- Check the upstream TorchAO compatibility table first during updates; this package must stay on the release line built for the local PyTorch lane rather than a nearby +git snapshot.
- Keep VERSION_SUFFIX empty for release builds unless upstream changes its versioning model; +git local versions bypass TorchAO's own compatibility gate and recreate avoidable import-time warnings.
- Keep ROCM_HOME=/opt/rocm in the build environment unless the local ROCm packaging layout changes. The host-visible hipcc wrapper may live under /usr/bin, but the headers and shared libraries still come from /opt/rocm.
- Re-verify the installed extension with readelf -d and ldd -r after each update. A clean package needs both a usable torch/lib runpath and zero unresolved ATen/Torch symbols once torch/lib is visible.
- Keep the PT2E union-alias patch until upstream TorchAO handles Python 3.14 typing.Union objects without assigning __module__ directly.
- Keep the repo-local tools/torchao_vllm_smoke.py helper passing for both the tiny serialized checkpoint and the Gemma 4 online quantization path. Treat the serialized Gemma 4 real-model checkpoint path as blocked until the TorchAO/vLLM tensor metadata mismatch is fixed.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
