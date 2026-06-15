# aocl-utils-gfx1151

## Maintenance Snapshot

- Recipe package key: `aocl_utils`
- Scaffold template: `cmake`
- Recipe build method: `cmake`
- Upstream repo: `https://github.com/amd/aocl-utils.git`
- Package version: `5.3.0`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `6`
- Recipe dependencies: `therock`
- Recorded reference packages: `aur/aocl-utils, aur/aocl-utils-aocc`
- Authoritative reference package: `aur/aocl-utils`
- Advisory reference packages: `aur/aocl-utils-aocc`
- Applied source patch files/actions: `0`

## Recipe notes

CPU feature detection library for AOCL-LibM.

Built WITHOUT LTO: AOCL-LibM links this .a with GNU ld (needed for
its hand-written AVX assembly), and GNU ld cannot read LLVM bitcode
objects that LTO produces.

Built WITHOUT clang-tidy: TheRock's clang-tidy crashes on AOCL-Utils
cleanup phase, and system clang-tidy doesn't understand -famd-opt.
CMAKE_CXX_CLANG_TIDY=/bin/true prevents auto-detection.

## Scaffold notes

- This scaffold is rebased onto the current AUR aocl-utils 1:5.3-1 package rather than the older aocc-specific variant.
- The package keeps pkgver 5.3.0 because upstream version.txt still reports 5.3.0, while the source archive follows the current upstream tag name 5.3.
- The older AUR aocl-utils-aocc package remains stale advisory context because it captures the AOCC-specific lane, even though the current non-AOCC aocl-utils package is the closer baseline for this toolchain.
- The recipe intentionally disables LTO because AOCL-LibM links AOCL-Utils archives with GNU ld.
- Build testing showed -famd-opt is a compile-time no-op here, so the scaffold keeps it out of the AOCL-Utils compile flags while still using amdclang as the compiler baseline.
- AOCL-Utils 5.3.0 renames upstream license files to LICENSE.txt and NOTICE.txt without changing the installed library/header layout used by this package.

## Intentional Divergences

- Uses amdclang as the compiler baseline but intentionally leaves AOCL-Utils itself off the more aggressive recipe flag bundle because build testing showed -famd-opt is a no-op here.
- Uses the upstream 5.3.0 release tarball while preserving local amdclang, clang-tidy, and LTO policy over the simpler AUR baseline.

## Update Notes

- When the AUR baseline changes, re-check license packaging and install layout against aur/aocl-utils first, then compare any AOCC-specific drift from aur/aocl-utils-aocc.
- The current AUR aocl-utils baseline is 1:5.3-1 because upstream exposes the 5.3 source archive through tag 5.3 while the source tree still reports AOCL-Utils 5.3.0.
- If the recipe starts carrying source patches here, convert them into patch files under patches/aocl-utils-gfx1151 rather than inline shell edits.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
