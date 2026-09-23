# TheRock ROCm Split Package Base

This directory is the canonical rendered package base for the local TheRock
ROCm split.

It is generated from:

- `generators/therock_split.py`
- `policies/therock-packages.toml`
- `templates/PKGBUILD.in`

## Refresh

Run:

```bash
python tools/render_therock_pkgbase.py --therock-root <staged-root>
```

That command:

- scans the staged or installed `opt/rocm` tree
- uses `pkgver` from `policies/therock-packages.toml`
- stamps repo-local `upstream/ai-notes/strix-halo` recipe provenance into the
  generated `PKGBUILD` and manifest
- rewrites the file lists and manifest in this directory

## Build expectation

The generated `PKGBUILD` expects `_THEROCK_ROOT` to point at a filesystem root
that contains `opt/rocm`. For a complete live local tree, `_THEROCK_ROOT=/` is
valid. For a staged install tree, point it at that staging root instead.

## Source lane

`policies/therock-packages.toml` targets TheRock 7.14.1 (`7.14.1-1`), the
C-line foundation F pick (#108). The rendered files in this directory are the
7.14.1 render (`7.14.1-1`, 68 packages), made from the pinned payload stage
after MIGraphX 2.16.1 was built into it. Render this directory only from that
complete stage.

The earlier lane was the upstream `therock-7.13` release. The host runs
`7.13.0-3`, the MIGraphX rebuild against protobuf 35.1 from the unmerged
`migraphx-protobuf-35-1-rebuild` branch, whose tooling changes were ported into
the 7.14.1 staging flow below.

## Staging the 7.14.1 payload

The repo stages the AMD dist tarball instead of building TheRock from source.
The `[payload]` table in `policies/therock-packages.toml` pins its URL, size,
and sha256; AMD publishes no checksum sidecar, so the sha256 was recorded at
first fetch. The tarball root is the ROCm prefix.

Steps, in order:

1. Stage the payload. The stage root comes from `--stage` or
   `THEROCK_STAGE_ROOT`. Expect 1.6 GiB for the tarball and about 8.3 GiB for
   the stage; `--remove-tarball` drops the tarball after extraction.

   ```bash
   python tools/stage_therock_payload.py --stage <stage> [--remove-tarball]
   ```

   The tool downloads the pinned URL into `<stage>.download/` (or
   `--download-dir`, `THEROCK_DOWNLOAD_DIR`), verifies size and sha256,
   extracts into `<stage>/opt/rocm`, and checks `.info/version` against the
   policy `pkgver`. `--tarball <file>` verifies and uses an existing download.
2. Optionally dry-render before MIGraphX exists. The render must be clean
   except for the missing MIGraphX payload:

   ```bash
   python tools/render_therock_pkgbase.py --therock-root <stage> \
     --output <scratch-dir> --pre-migraphx-dry-render
   ```

   `--pre-migraphx-dry-render` turns the missing
   `libmigraphx_onnx.so` soname source into a `SONAME_DEPEND_SKIPPED` warning
   and refuses any output under `packages/`.
3. Build MIGraphX into the stage with
   `tools/stage_migraphx_for_therock.zsh --stage <stage>`. It fetches
   AMDMIGraphX 2.16.1 (`2487b688`) by SHA, configures it against the stage only
   (stage `amdclang`, `ROCM_PATH`, and `CMAKE_PREFIX_PATH`, with no host
   `/opt/rocm` fallback), takes `pybind11_DIR` from
   `python -m pybind11 --cmakedir`, and builds the ONNX and TF parsers against
   an isolated protobuf 36.1 / abseil-cpp 20260817 prefix populated from the
   sha256-pinned Arch packages. It derives the protobuf and utf8_validity
   SONAMEs from that prefix, rejects parser libraries that link any other
   protobuf, utf8_validity, or Abseil ABI, checks the staged Python import, and
   then renders this directory and previews the amerge plan. The build needs
   CPython 3.14.7 (`python-gfx1151`) as the active `python` and
   `python3.14-config`. MLIR stays off; see
   [the no-MLIR stubs](../../docs/patches.md#migraphx-therock-stage). The
   same section records the `rocm_add_version_resource` configure shim for
   the staged rocm-cmake 0.14.0.
4. Build the split family with `_THEROCK_ROOT=<stage>`.

`migraphx-gfx1151` gets its `libprotobuf.so=<ver>-64` depend from the staged
parser's `DT_NEEDED` through the policy's `soname_depends`, so the depend
follows the protobuf that MIGraphX was built against. Moving the host to
protobuf 36.1 also moves `libphonenumber` and `python-protobuf`, which pin
protobuf 35.1, so the install transaction must include them.

## kpack device-code archives

The 7.14.1 gfx1151 dist tarball is kpack-split. Ten libraries carry a
`.rocm_kpack_ref` marker and a `NOBITS` `.hip_fatbin`, so they hold no gfx1151
kernels on disk. `libamdhip64` loads their kernels through `librocm_kpack` from
the archives in `opt/rocm/.kpack/`, found relative to the library directory:

| Archive | Owner | Libraries |
| --- | --- | --- |
| `blas_lib_gfx1151.kpack` | `rocblas-gfx1151` | rocBLAS, hipBLASLt, rocSPARSE, rocSOLVER, hipSPARSELt |
| `fft_lib_gfx1151.kpack` | `rocfft-gfx1151` | rocFFT |
| `rand_lib_gfx1151.kpack` | `rocrand-gfx1151` | rocRAND |
| `rccl_lib_gfx1151.kpack` | `rccl-gfx1151` | RCCL |
| `hiptensor_lib_gfx1151.kpack` | `hiptensor-gfx1151` | hipTensor |
| `rocalution_lib_gfx1151.kpack` | `rocalution-gfx1151` | rocALUTION |

The libraries must stay in `/opt/rocm/lib` and the archives in
`/opt/rocm/.kpack/`. Every package whose library uses `blas_lib` depends
directly on `rocblas-gfx1151`. The generator enforces this with
`KPACK_REF_UNOWNED`. With `.kpack` ignored, as the 7.13 policy had it, the
render and build pass and the first kernel launch fails
(`ROCRAND_STATUS_LAUNCH_FAILURE` in the gate-0 rocRAND probe). Installed
validation therefore needs one kernel per archive family, not only rocBLAS.

## 7.14.1 payload decisions

- New packages: `rocalution-gfx1151` (Arch `rocalution` depends) and
  `hipfile-gfx1151` (hipFile 0.3.0 plus the `ais-check` and `ais-stats`
  tools). `hiptensor-gfx1151` now has payload. All three are in
  `rocm-hip-libraries-gfx1151`.
- Not packaged: rocJITsu (the EMULATION group; no payload ELF links
  `librocjitsu` and nothing in this stack consumes it), the WSL `rocdxg` shim,
  and the rocprofiler-sdk test payload.
- Re-homed: the rocprof-trace-decoder headers and CMake files go to
  `rocprofiler-systems-gfx1151`, which already owns the library; the top-level
  `nccl.h`, `nccl_device.h`, and `nccl_device/` headers go to `rccl-gfx1151`;
  `hipdnn_frontend_python.abi3.so` goes to `miopen-hip-gfx1151` with hipDNN;
  `hrr-playback` goes to `hip-runtime-amd-gfx1151`; and the `amdllvm`
  symlink goes to `rocm-llvm-gfx1151`.
- `bin/rocprof-compute` is now an upstream Python launcher, owned by
  `rocprofiler-compute-gfx1151`. The 7.13 policy made that path a symlink
  in `rocprofiler-compute-gfx1151`, and the `rocprof` binary prefix gave the
  new launcher to `rocprofiler-systems-gfx1151`, so both packages shipped the
  path and could not be installed together.
- CI build paths (`/__w/rockrel/...`) in `rocprofiler-sdk-config.cmake`,
  `hsakmtTargets.cmake`, `nlohmann_json.pc`, and `flatbuffers.pc` are rewritten
  at package time, and each package fails with `CI_PATH_LEAK` if one survives.
  The 7.13 rocm-smi fix-ups matched nothing in 7.14.1 and were removed.

## 7.14.1 removals and upstream gaps

The generator is payload-driven, so removals are silent. The 7.14.1 payload
drops:

- the IREE compiler and the fusilli hipDNN plugin; the `iree`, `IREE`,
  `IREECompiler`, `iree_compiler`, and IREE-supplied `mlir-c` aliases are gone
  from policy;
- the vendored top-level `opt/rocm/libhipcxx/` tree (816 files from
  `hip-gfx1151`); `include/libhipcxx` and `lib/cmake/libhipcxx` remain;
- the hipSOLVER Fortran library (`libhipsolver_fortran.so*`);
- MAGMA entirely, so `magma-gfx1151` no longer renders (see
  [magma after 7.13](#magma-after-713));
- `share/miopen/db/*`, which held only gfx908/gfx90a/gfx942/gfx950 data.

Upstream gap: the tarball ships the rocpd and roctx Python bindings (and the
rocprofiler-systems `libpyrocprofsys` extension) only for CPython 3.10-3.13.
The host is 3.14-only, so those ABI copies are ignored, and
`rocprofiler-sdk-rocpd-gfx1151` and `rocprofiler-sdk-roctx-gfx1151` ship
without Python bindings until TheRock publishes 3.14 builds.

## rocm-core baseline

`rocm-core-gfx1151` now treats CachyOS `rocm-core` as the distro-integration
baseline while still packaging the newer TheRock 7.13 payload.

That means the split package intentionally carries the small Cachy-style
integration surface on top of the scanned TheRock files:

- `etc/ld.so.conf.d/rocm.conf`
- shell path setup in `etc/profile.d/rocm.sh` and
  `usr/share/fish/vendor_conf.d/rocm.fish`
- the `opt/rocm/bin/rdhc` wrapper plus `opt/rocm/share/rdhc/*`
- license copies under `opt/rocm/share/doc/rocm-core/` and
  `usr/share/licenses/rocm-core/`

The remaining file-list delta against Cachy should be TheRock-owned additions
or version-lane differences only: `nlohmann` headers, `.hipInfo`,
`share/modulefiles`, `share/therock`, and the expected `rocmCoreTargets` /
`librocm-core.so` version suffix changes.

## magma after 7.13

The 7.14.1 payload has no MAGMA, so this family no longer builds
`magma-gfx1151`. The host still has `magma-gfx1151 7.13.0-3` installed, and
the installed `python-pytorch-opt-rocm-gfx1151 2.12.0-4` needs it:
`libtorch_hip.so` has `DT_NEEDED libmagma.so`. Its PKGBUILD does not declare
that depend, so pacman does not know about it. The 7.14.1 install
transaction must therefore keep `magma-gfx1151` until the PyTorch lane is
rebuilt without MAGMA or given another MAGMA source. Remove it in that
transaction only once no installed package needs `libmagma.so`. The sonames
`libmagma.so` needs (`libhipblas.so.3`, `libhipsparse.so.4`, and
`libamdhip64.so.7`) still exist in 7.14.1, but nobody has tested the 7.13
MAGMA build against the 7.14.1 libraries.

## magma baseline (7.13)

`magma-gfx1151` follows Arch `magma-hip` package metadata for its public
package interface while using the TheRock payload. It provides and replaces
both `magma-hip` and the legacy `hipmagma` name, and maps Arch's ROCm runtime
dependencies to the local gfx1151 split packages.
