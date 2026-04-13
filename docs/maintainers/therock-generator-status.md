# TheRock Generator Status

The first-pass TheRock split generator is functional and already underpins the
live TheRock package family in this repo. The current policy is sufficient to:

- scan the installed TheRock payload
- assign every discovered path to a package owner or an intentional ignore rule
- emit a split-package `PKGBUILD`
- emit per-package file lists
- emit a manifest describing the generated package set

## Current result

The canonical rendered output is produced with:

`python tools/render_therock_pkgbase.py --recipe-root /path/to/ai-notes`

That writes the buildable split `pkgbase` into `packages/therock-gfx1151/` and
stamps `pkgver` from the recipe repo's folder-local git history.

The generated family now includes the expected ROCm runtime, math, profiling,
debugging, OpenCL, and ML package surface, plus two internal support packages
that emerged from the TheRock tree itself:

- `rocm-host-math-gfx1151`
- `rocm-sysdeps-gfx1151`

These do not correspond neatly to standard Arch packages, so they are being
treated as local TheRock support packages rather than replacements for
system-wide `openblas`, `suitesparse`, or other distro packages.

## What changed

The generator and policy now handle:

- root-level include files by prefix instead of misclassifying them as component
  names
- longest-prefix ownership matching to avoid false ambiguity like `hipblas`
  versus `hipblaslt`
- whole-runtime subtrees under `lib/` such as:
  `hipblaslt`, `rocblas`, `rocfft`, `rocsparse`, `opencl`, `rdc`,
  `rocprofiler-*`, `roctracer`, `host-math`, and `rocm_sysdeps`
- vendored `libhipcxx` header and CMake payloads while ignoring its source/test
  debris
- structured ignore rules for known sample and test artifacts

## Current caveat

Generator success is necessary, not sufficient. Any meaningful TheRock update
still needs:

1. a clean render
2. successful package builds
3. a publishable local repo refresh
4. install and smoke validation on the reference host

## Remaining caveat

The generator is no longer exploratory. The follow-up work is maintenance:

- keep policy current when TheRock adds or reshapes components
- keep dependency and replacement metadata healthy
- keep the generated family aligned with the local repo and live cutover story
