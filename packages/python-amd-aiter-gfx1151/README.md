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
- Applied source patch files/actions: `9`

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
- Keep the gfx1151 RDNA 3.5 header fixes as package-local source patches applied before wheel build, split between the `vec_convert.h` packed-op fallbacks and the `hip_reduce.h` wave32/DPP compatibility rewrite.
- Keep the installed-system JIT runtime patch unless upstream fixes both assumptions itself: `hipcc` on the ambient PATH, and package-relative import of JIT-built modules even after copying the writable JIT tree out of read-only site-packages.
- Keep the gfx1x AITER-side MoE compatibility patches that are genuinely local: unknown-gfx probing, missing 1-stage ASM metadata, and CK 2-stage splitk normalization/forwarding. The current validated Gemma 4 26B-A4B lane uses TRITON backend for Unquantized MoE, so any attempt to move that model back onto AITER fused-MoE should be treated as fresh validation work, not as a presumed default-lane dependency.

## Intentional Divergences

- There is no standalone AITER package in Arch-family packaging; this package is recipe-first and aligned to the vendored PyTorch submodule lane.
- Carries explicit package-local source patches for gfx1151 RDNA 3.5 header compatibility, split between vec_convert packed-op fallbacks and hip_reduce wave32/DPP compatibility, rather than leaving those fixes as manual post-build mutations.
- Carries an installed-system JIT runtime patch so AITER can find `hipcc` and import JIT-built modules from the writable user cache on read-only site-packages installs.
- Carries the gfx1x AITER-side MoE compatibility patches that are safe to keep local: unknown-gfx probing, missing 1-stage ASM metadata handling, and CK 2-stage splitk normalization/forwarding for AITER fused-MoE experiments and other non-Gemma lanes. The current validated Gemma 4 default path still uses TRITON for unquantized MoE.

## Update Notes

- Update AITER in lockstep with the paired PyTorch source lane so CK and generated kernel expectations stay aligned.
- Treat FlyDSL as a separate tracked package story; do not silently fold an unpublished wheel into this package.
- Keep the installed-system JIT runtime patch until upstream AITER stops assuming `hipcc` is on the ambient PATH and correctly imports modules copied to the writable user JIT cache from read-only site-packages installs.
- Keep the package's explicit ROCm toolchain exports in `build()` until upstream AITER stops probing `hipconfig` and `hipcc` through ambient shell state. The concrete build failure was `Could not find hipconfig in PATH or ROCM_HOME(/usr)`.
- Keep the split RDNA header carries narrow: `0001-gfx1151-rdna35-header-compat.patch` now covers only the `vec_convert.h` gfx11 packed-op fallbacks, while `0006-rdna35-hip-reduce-wave32-dpp-compat.patch` carries the broader `hip_reduce.h` wave32/DPP rewrite. If that area is revisited, re-verify `hip_reduce.h` on its own instead of recombining unrelated header edits.
- Keep the unknown-gfx 2-stage fallback, missing-1-stage-metadata tuner skip, and CK 2-stage splitk normalization/forwarding fix until upstream AITER handles those gfx1x cases directly. Do not reintroduce an unquantized `torch_moe` fallback here: the concrete reference-host failure was `google/gemma-4-26B-A4B-it` generating corrupted text after such a fallback ran on AITER-shuffled weights.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
