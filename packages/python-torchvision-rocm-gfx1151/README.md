# python-torchvision-rocm-gfx1151

## Maintenance Snapshot

- Recipe package key: `torchvision`
- Scaffold template: `python-project-torchvision-rocm`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/pytorch/vision.git`
- Derived pkgver seed: `0.26.0.r8.d20260317.gad42886`
- Recipe steps: `12, 13`
- Recipe dependencies: `pytorch`
- Recorded reference packages: `aur/python-torchvision-rocm, aur/python-torchvision-rocm-bin, extra/python-torchvision`
- Authoritative reference package: `aur/python-torchvision-rocm`
- Advisory reference packages: `aur/python-torchvision-rocm-bin, extra/python-torchvision`
- Applied source patch files/actions: `0`

## Recipe notes

Built against source PyTorch (must find torch headers in pytorch/
source tree, not from a pip install).

## Scaffold notes

- Authoritative base: AUR python-torchvision-rocm 0.26.0-1 because it is the closest maintained ROCm packaging lane for torchvision.
- Advisory references: python-torchvision-rocm-bin for packaging shape around the ROCm variant and repo python-torchvision for generic Arch Python packaging conventions.
- The recipe must build against the source-tree torch headers from the paired PyTorch package, not against an arbitrary preinstalled wheel.
- Keep the recipe's TorchVision environment intact: FORCE_CUDA=0, FORCE_MPS=0, empty TORCH_CUDA_ARCH_LIST, and pip-wheel packaging without build isolation.

## Intentional Divergences

- Builds against the paired optimized PyTorch package tree rather than an arbitrary preinstalled torch wheel.
- Follows the recipe's ROCm wheel-build environment instead of the generic upstream CUDA-oriented defaults.

## Update Notes

- Re-check the package against the current AUR ROCm variant first, then compare any generic Arch torchvision changes that affect Python packaging or dependency handling.
- Keep the temporary build-only rocsolver soname shim out of the final package story; if it reappears, fix the true build dependency lane instead.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
