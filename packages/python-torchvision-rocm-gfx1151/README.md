# python-torchvision-rocm-gfx1151

## Maintenance Snapshot

- Recipe package key: `torchvision`
- Scaffold template: `python-project-torchvision-rocm`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/pytorch/vision.git`
- Package version: `0.26.0`
- Recipe revision: `a1d7a68 (20260427, 16 path commits)`
- Recipe steps: `13, 14`
- Recipe dependencies: `pytorch`
- Recorded reference packages: `aur/python-torchvision-rocm, aur/python-torchvision-rocm-bin, extra/python-torchvision`
- Authoritative reference package: `aur/python-torchvision-rocm`
- Advisory reference packages: `aur/python-torchvision-rocm-bin, extra/python-torchvision`
- Applied source patch files/actions: `1`

## Recipe notes

Built against source PyTorch (must find torch headers in pytorch/
source tree, not from a pip install).

## Scaffold notes

- Authoritative base: AUR python-torchvision-rocm 0.26.0-1 because it is the closest maintained ROCm packaging lane for torchvision.
- Advisory references: python-torchvision-rocm-bin for packaging shape around the ROCm variant and repo python-torchvision for generic Arch Python packaging conventions.
- The recipe must build against the source-tree torch headers from the paired PyTorch package, not against an arbitrary preinstalled wheel.
- Carry the setup.py source patch that makes ROCm HIP builds honor NVCC_FLAGS so the package-level source-path sanitizer also applies to .hip translation units.
- The paired PyTorch package is now import-clean against librocsolver.so.1, so this scaffold should not reintroduce the earlier build-only librocsolver.so.0 shim.
- Keep the recipe's TorchVision environment intact: FORCE_CUDA=0, FORCE_MPS=0, empty TORCH_CUDA_ARCH_LIST, and pip-wheel packaging without build isolation.

## Intentional Divergences

- Builds against the paired optimized PyTorch package tree rather than an arbitrary preinstalled torch wheel.
- Follows the recipe's ROCm wheel-build environment instead of the generic upstream CUDA-oriented defaults.

## Update Notes

- Re-check the package against the current AUR ROCm variant first, then compare any generic Arch torchvision changes that affect Python packaging or dependency handling.
- Keep the paired PyTorch package import-clean enough that TorchVision does not need any build-only rocsolver soname shim. If a shim becomes necessary again, treat that as a PyTorch/runtime-lane regression rather than reintroducing the workaround here.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
