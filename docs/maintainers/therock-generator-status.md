# TheRock Generator Status

The first-pass TheRock split generator is functional and already underpins the
live TheRock package family in this repo. The current policy is sufficient to:

- scan the installed TheRock payload
- assign every discovered path to a package owner or an intentional ignore rule
- emit a split-package `PKGBUILD`
- emit per-package file lists
- emit a manifest describing the generated package set

## Current result

The canonical rendered output is produced from a complete staged root:

`python tools/render_therock_pkgbase.py --therock-root <staged-root>`

That writes the buildable split `pkgbase` into `packages/therock-gfx1151/` and
stamps `pkgver` from `policies/therock-packages.toml`. The repo-local
`upstream/ai-notes/strix-halo` git history is recorded as recipe provenance.
Using `/` is valid only when the live install root contains every payload that
should remain rendered.

The generated family is payload-driven. The current rendered output includes
68 of the 70 policy-defined packages. Two packages are present in policy
metadata but not rendered because their expected installed payloads are absent
from the staged root used for the render:

- `hipfort-gfx1151`
- `mivisionx-gfx1151`

`rocm-sysdeps-gfx1151` is rendered as an internal TheRock support package. It
does not correspond neatly to a standard Arch package, so it is treated as
local TheRock support payload rather than a replacement for system-wide
`openblas`, `suitesparse`, or other distro packages.

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
- removal of stale per-package file lists when a rerender no longer contains
  that package's payload
- package copy from staged roots outside `/` without embedding the staging path
  in packaged file paths

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
- audit `hipfort-gfx1151` and `mivisionx-gfx1151` when a staged TheRock root
  contains those payloads
