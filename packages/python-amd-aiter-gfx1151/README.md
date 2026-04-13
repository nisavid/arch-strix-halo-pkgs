# python-amd-aiter-gfx1151

## Maintenance Snapshot

- Recipe package key: `aiter`
- Scaffold template: `python-project-aiter`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/ROCm/aiter.git`
- Derived pkgver seed: `0.1.0.r8.d20260317.gad42886`
- Recipe steps: `28`
- Recipe dependencies: `pytorch, vllm`
- Recorded reference packages: `extra/python-pytorch-opt-rocm, extra/python-pytorch-rocm`
- Authoritative reference package: `none`
- Advisory reference packages: `extra/python-pytorch-opt-rocm, extra/python-pytorch-rocm`
- Applied source patch files/actions: `4`

## Recipe notes

Rebuilt from PyTorch's third_party/aiter/ submodule to align CK ABI
with the CK headers used by AITER's JIT at runtime.

PREBUILD_KERNELS=0: skip 45-minute full kernel precompilation.
Kernels are JIT-compiled on first use instead.

After wheel install, two header patches are applied to the installed
aiter_meta/csrc/include/ files for gfx1151 RDNA 3.5 compatibility.

## Scaffold notes

- There is no standalone Arch, CachyOS, or AUR aiter package. The closest packaging lane is the PyTorch ROCm pkgbase that vendors the same submodule, so that pkgbase is advisory only.
- The recipe rebuilds AITER from PyTorch's vendored third_party/aiter copy so its CK ABI stays aligned with the paired PyTorch tree.
- Upstream AITER declares pandas as a real dependency and FlyDSL as an optional acceleration path. Keep pandas in the package metadata, and package FlyDSL separately rather than silently depending on an unpublished wheel.
- Keep the gfx1151 RDNA 3.5 header fixes as a package-local source patch applied before wheel build, not as post-install file replacement.

## Intentional Divergences

- There is no standalone AITER package in Arch-family packaging; this package is recipe-first and aligned to the vendored PyTorch submodule lane.
- Carries an explicit package-local source patch for gfx1151 RDNA 3.5 header compatibility rather than leaving those fixes as manual post-build mutations.

## Update Notes

- Update AITER in lockstep with the paired PyTorch source lane so CK and generated kernel expectations stay aligned.
- Treat FlyDSL as a separate tracked package story; do not silently fold an unpublished wheel into this package.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
