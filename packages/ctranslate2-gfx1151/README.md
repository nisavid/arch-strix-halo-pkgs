# ctranslate2-gfx1151

## Maintenance Snapshot

- Package version: `4.7.2`
- Upstream repo: `https://github.com/OpenNMT/CTranslate2`
- Source lane: OpenNMT tag `v4.7.2` with upstream `WITH_HIP=ON`
- Recorded reference packages: `aur/ctranslate2`, `ROCm/CTranslate2`
- Authoritative reference package: `aur/ctranslate2`
- Advisory reference packages: `ROCm/CTranslate2`, AMD ROCm CTranslate2 blog
- Applied source patch files/actions: `1`

## Package Shape

This split package provides:

- `ctranslate2-gfx1151`, the C++ runtime built with ROCm HIP for `gfx1151`.
- `python-ctranslate2-gfx1151`, the Python bindings used by
  `faster-whisper` and CTranslate2 converters.

The package follows upstream OpenNMT `v4.7.2`, not the older ROCm fork, because
the tagged upstream release now exposes `WITH_HIP=ON` directly. The ROCm fork
and AMD blog remain useful advisory references for examples and deployment
expectations, but the packaged source should stay on the tagged OpenNMT release
lane until a fork-only fix is locally required.

## Intentional Divergences

- Enables `WITH_HIP=ON` and targets `CMAKE_HIP_ARCHITECTURES=gfx1151`.
- Uses ROCm clang directly as `CMAKE_HIP_COMPILER`; CMake rejects the `hipcc`
  wrapper for this package.
- Disables the optional CTranslate2 CLI target. The Python/faster-whisper lane
  needs the library and Python extension, and a scratch CLI build failed under
  clang 22 because vendored `cxxopts.hpp` did not include `cstdint`.
- Relaxes the exact `pybind11==2.11.1` build requirement so the package can use
  Arch's system `pybind11`.
- Keeps `WITH_MKL=OFF`, `WITH_DNNL=OFF`, `WITH_OPENBLAS=ON`, and
  `WITH_RUY=ON`, matching the current AUR CPU package's OpenBLAS/Ruy baseline
  while adding the HIP backend.

## Validation Notes

A package build on 2026-05-24 completed through
`tools/amerge build ctranslate2-gfx1151`, producing both split packages:

- `ctranslate2-gfx1151-4.7.2-1-x86_64.pkg.tar.zst`
- `python-ctranslate2-gfx1151-4.7.2-1-x86_64.pkg.tar.zst`

The build configured OpenNMT CTranslate2 4.7.2 with `WITH_HIP=ON`,
`CMAKE_HIP_ARCHITECTURES=gfx1151`, and ROCm clang as the HIP compiler. It
builds the library and Python wheel after relaxing the pybind11 requirement.
The package uses `/usr/bin/python` for build/install steps so agent-local
Python wrappers cannot redirect bytecode caches into host-private cache paths.

The package freshness family was checked on 2026-05-24 and is current for the
OpenNMT 4.7.2 release, AUR `ctranslate2 4.7.1-1`, and the tracked ROCm fork
`amd_dev` commit.

The installable `4.7.2-1` package metadata depends on Arch's `openmp` package
for `libomp.so`.

The root deploy target selects both split outputs:

```sh
tools/amerge deploy ctranslate2-gfx1151
```

Both split packages are published to the local `strix-halo-gfx1151` repo and
installed from that repo. Installed Python smoke passes with CTranslate2 4.7.2
reporting one ROCm device and CUDA/HIP compute types including `float16`,
`bfloat16`, `float32`, and int8 variants. `faster_whisper` imports against the
installed CTranslate2 module.

The Open WebUI STT consumer path passed on 2026-05-24 against the installed
`open-webui 0.9.5-2`, `python-faster-whisper 1.2.1-1`, and CTranslate2 split
packages. The smoke used Open WebUI's `transcribe` path with
`USE_CUDA_DOCKER=true`, Open WebUI selected `DEVICE_TYPE=cuda`, and
`Systran/faster-whisper-tiny.en` produced non-empty English transcript text
from a generated WAV file.

## Update Notes

- Re-check the current AUR `ctranslate2` package first for Arch packaging
  drift, then compare upstream OpenNMT release notes and the ROCm fork only for
  HIP-specific fixes.
- If upstream fixes the clang 22 `cxxopts.hpp` include issue, consider enabling
  the CLI target and packaging the installed CLI binaries.
- If upstream changes HIP build options, re-run the configure probe before
  changing package metadata.
- Keep Open WebUI STT validation separate from package-build proof when future
  CTranslate2, faster-whisper, Open WebUI, or ROCm package changes affect this
  lane.

## Maintainer Starting Points

- `PKGBUILD`
- `0001-relax-pybind11-build-requirement.patch`
- Upstream install docs: `https://opennmt.net/CTranslate2/installation.html`
- AMD ROCm CTranslate2 blog:
  `https://rocm.blogs.amd.com/artificial-intelligence/ctranslate2/README.html`
