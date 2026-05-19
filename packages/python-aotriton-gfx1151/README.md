# python-aotriton-gfx1151

## Maintenance Snapshot

- Recipe package key: `aotriton`
- Scaffold template: `python-project-aotriton`
- Recipe build method: `cmake`
- Upstream repo: `https://github.com/ROCm/aotriton.git`
- Package version: `0.12b`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `18, 19`
- Recipe dependencies: `triton`
- Recorded reference packages: `extra/python-aotriton, cachyos-extra-znver4/python-aotriton`
- Authoritative reference package: `extra/python-aotriton`
- Advisory reference packages: `cachyos-extra-znver4/python-aotriton`
- Applied source patch files/actions: `1`

## Recipe notes

Pre-compiles Triton attention kernels to HSACO (ahead-of-time),
eliminating JIT compilation at inference time. v2 with Python
bindings. gfx1151 explicitly targeted via AOTRITON_TARGET_ARCH.

## Scaffold notes

- Arch python-aotriton remains at 0.11.2b-1; the local source lane adopts upstream 0.12b because gfx1151 is now promoted out of the experimental target set.
- The recipe and Arch baseline are unusually close here, so preserve Arch's patching approach wherever possible and only layer on the recipe's compiler and install details.
- Do not carry forward Arch's broader multi-arch target matrix here. The Strix Halo recipe intentionally narrows AOTRITON_TARGET_ARCH to gfx1151 only so the build does not waste time compiling irrelevant kernels.
- The nested vendored Triton build must explicitly disable TRITON_BUILD_UT, otherwise it spends time linking irrelevant C++ unit-test binaries and can fail there before the Python runtime package is produced.
- The nested vendored Triton build must also inherit amdclang via CC/CXX and start from a fresh triton_build directory. Reusing a stale g++-configured build tree can reproduce GCC 15 LTO warning-as-error failures in GenericSwizzling.cpp even after the PKGBUILD is fixed.
- AOTriton's release-owned submodules are pinned as package sources and staged into third_party during prepare(); do not reintroduce network submodule updates.
- Keep vendored Triton's download, pip, and bytecode caches rooted under srcdir during package builds. Its setup.py otherwise derives TRITON_CACHE_PATH from the builder's home directory, which can leak host-specific paths and fail under sandboxed read-only homes.
- Patch the vendored Triton wheel build so optional NVIDIA plugin wiring is backend-gated and the CUDA GSan runtime is not built as an unconditional package artifact. AOTriton does not use CUDA GSan for gfx1151, and that runtime depends on CUDA/GCC layout assumptions that are unrelated to this package.
- The vendored Triton submodule also needs the same Python-3.14 ast.Num compatibility cherry-pick used by python-triton-gfx1151, otherwise AOTriton kernel generation fails inside v3python/compile.py after the nested Triton wheel already built successfully.

## Intentional Divergences

- This package stays close to the Arch baseline but deliberately narrows the target arch set to gfx1151 and reuses the recipe's amdclang build lane.
- The nested vendored Triton build is part of the package story here and must carry the same Python-3.14 compatibility patching as the standalone Triton package.

## Update Notes

- When updating, compare against Arch first because this is one of the closest recipe-to-baseline packages in the stack.
- Keep the package on stable AOTriton releases for gfx1151. The 0.11.210b and 0.11.52b tech previews are intentionally not adopted because they target gfx942 ASAN and gfx1250 preview builds rather than this package's Strix Halo lane.
- Preserve the reuse-build logic and stale-build-tree cleanup; interrupted AOTriton builds otherwise leave a misleading broken state behind.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
