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
66 of the 70 policy-defined packages. Four packages are present in policy
metadata but not rendered because their expected installed payloads are absent
from the staged root used for the render:

- `hipfort-gfx1151`
- `hiptensor-gfx1151`
- `mivisionx-gfx1151`
- `rpp-gfx1151`

The 2026-04-25 coverage audit confirmed this is a staged-payload boundary, not
a missing package metadata boundary. The live `/opt/rocm`, current
`packages/therock-gfx1151/filelists/`, and current package artifacts contain no
hipFORT or MIVisionX payload. Arch-family package layouts show the expected
payload shapes, and policy aliases now cover representative future TheRock
paths:

- `hipfort-gfx1151`: `hipfc`, `include/hipfort/`, `lib/cmake/hipfort/`,
  `libhipfort-*`, `libexec/hipfort/`, and `share/hipfort/`
- `mivisionx-gfx1151`: `mv_compile`, `runvx`, `include/mivisionx/`,
  `libopenvx`, `libvx_*`, and `libexec/mivisionx/`

A future staged root that contains those payloads should render package
functions and file lists instead of failing with `NEW_THEROCK_PACKAGE_CLASS`.

`rocm-sysdeps-gfx1151` is rendered as an internal TheRock support package. It
does not correspond neatly to a standard Arch package, so it is treated as
local TheRock support payload rather than a replacement for system-wide
`openblas`, `suitesparse`, or other distro packages.

The 2026-04-25 baseline audit aligned `rocm-debug-agent-gfx1151` with the
current Arch/CachyOS `rocr-debug-agent` package shape: the local split package
now provides and replaces `rocr-debug-agent` while continuing to provide
`rocm-debug-agent`, and it depends on the local `rocm-core`, `hip-runtime-amd`,
and `rocm-dbgapi` split packages.

The same audit stopped rendering fileless compatibility packages for
`hiptensor-gfx1151` and `rpp-gfx1151`. Current Arch/CachyOS `hiptensor` and
`rpp` are real payload packages, while the current staged TheRock root contains
no matching payloads. The local HIP and ML meta packages therefore no longer
depend on those names until a staged root can render real package contents.
Because older publishes may still have zero-payload archives for those names,
deployment needs explicit stale local repo and installed-package cleanup.

The baseline audit also tightened core runtime dependency metadata for
`comgr`, `hsa-rocr`, `rocminfo`, `rocm-device-libs`,
`rocm-language-runtime`, `rocm-hip-runtime`, `hip-runtime-amd`, `rocm-cmake`,
`rocm-smi-lib`, `amdsmi`, `rocm-opencl-runtime`, `rocm-opencl-sdk`, and
`rocm-dbgapi`. The local split packages now mirror the Arch-family dependency
shape while substituting local `-gfx1151` ROCm package names and
`rocm-sysdeps-gfx1151` where TheRock bundles support libraries. The OpenCL
runtime no longer claims to provide the ICD loader; it provides the OpenCL
driver and depends on the system loader instead.

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
- rerender `hipfort-gfx1151`, `hiptensor-gfx1151`, `mivisionx-gfx1151`, and
  `rpp-gfx1151` when a staged TheRock root contains those payloads
- continue the Arch/CachyOS dependency audit for math, profiler, and ML split
  packages
