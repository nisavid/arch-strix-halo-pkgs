# python-triton-gfx1151

## Maintenance Snapshot

- Recipe package key: `triton`
- Scaffold template: `python-project-triton-rocm`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/ROCm/triton.git`
- Package version: `3.8.0+git669b31ac`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `15, 16, 17`
- Recipe dependencies: `therock, pytorch`
- Recorded reference packages: `extra/python-triton, cachyos-extra-znver4/python-triton`
- Authoritative reference package: `extra/python-triton`
- Advisory reference packages: `cachyos-extra-znver4/python-triton`
- Applied source patch files/actions: `2`

## Recipe notes

ROCm Triton release lane. The package follows the Triton commit that the
packaged ROCm PyTorch commit pins, and builds offline against the upstream LLVM
build that Triton's `cmake/llvm-info.json` names. Do not point it at TheRock
LLVM.

When switching compilation configurations, clear stale Inductor and Triton
caches before diagnosing mismatched guard-expression failures. The vLLM
compile cache is config-hash-keyed and does not require routine manual
clearing.


## Scaffold notes

- Authoritative base: Arch python-triton for distro integration and Python-3.14 carry patches.
- The recipe swaps in ROCm/triton instead of upstream triton-lang/triton. That makes Arch's package an advisory base rather than a source-identical one.
- Triton 3.8 keeps `pyproject.toml` and `setup.py` at the repo root; the renderer builds and installs from there, not from `python/`.
- Do not point Triton at TheRock's LLVM. It needs the exact LLVM revision in `cmake/llvm-info.json`; the renderer exports `LLVM_SYSPATH` to the unpacked `triton_llvm_dir` tarball.
- The `rocm-llvm-gfx1151` makedepend does not break that rule. It supplies the `amdclang` that `_setup_compiler_env` builds the extension with, not the LLVM that Triton links; keep it.
- The renderer caps concurrent links with `TRITON_PARALLEL_LINK_JOBS` (default 2), because each link pulls in static LLVM and MLIR.
- Rebuild and reinstall `python-triton-gfx1151` after patch-carry changes before treating compiled vLLM probes as repaired on the host.

## Intentional Divergences

- Uses Arch's Python packaging and integration baseline but deliberately swaps in ROCm/triton `release/internal/3.8.x` for the source lane: the exact Triton commit that the packaged ROCm PyTorch `release/2.12` commit pins in `.ci/docker/ci_commit_pins/triton.txt`.
- Builds against the upstream LLVM build that Triton's `cmake/llvm-info.json` names (`llvm-5f07f818-ubuntu-x64-1`), pinned in source=() by sha256, instead of TheRock's LLVM. Arch builds triton-lang's LLVM fork from source instead.

## Update Notes

- Take the Triton commit from the packaged ROCm PyTorch commit's `.ci/docker/ci_commit_pins/triton.txt`; do not follow the `release/internal/3.8.x` head on its own.
- On each source move, re-read `cmake/llvm-info.json`. When `llvm_hash`, `build_number` or the `ubuntu-x64` sha256 changes, update the LLVM tarball source ref, its sha256 and `triton_llvm_dir` together. `cmake/llvm-build-info.json` is not read by the build.
- The build is offline (`TRITON_OFFLINE_BUILD=ON`): LLVM comes from the pinned tarball and nlohmann-json from the system (`JSON_SYSPATH=/usr`). Upstream pins nlohmann-json v3.11.3 in `cmake/json-version.txt`; the header-only Arch package is newer.
- Keep pkgver and provides aligned with the wheel version from setup.py: `3.8.0` plus the `+git<short-hash>` suffix it adds for a non-release git branch, which is what a makepkg checkout is.
- Check Arch's current Triton Python packaging for Python-version fixes and install layout changes.
- Keep local source edits as patch files; this package is a likely upstream-candidate area.
- The 3.0-era `AttrsDescriptor.__repr__` patch was dropped at 3.8: the class no longer exists, and torch 2.12 Inductor takes its dict path when the class is absent.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
