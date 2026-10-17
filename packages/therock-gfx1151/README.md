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

`policies/therock-packages.toml` targets TheRock 7.14.1 (`7.14.1-2`), the
C-line foundation F pick (#108). The rendered files in this directory are the
`7.14.1-2` render (68 packages), made from the pinned payload stage with the
MIGraphX 2.16.1 payload in it. Render this directory only from that complete
stage.

`7.14.1-2` repackages `7.14.1-1` without recompiling anything. Its file lists
equal the `7.14.1-1` lists; it adds the MIGraphX Abseil range, the RUNPATH
rewrites and checks in [RUNPATH and RPATH](#runpath-and-rpath), and the
rocprofiler-sdk depends inversion. Its stage is the pinned payload with the
staged `migraphx-gfx1151-7.14.1-1` archive's `opt` tree extracted over it
(`bsdtar -xpf <archive> -C <stage> opt`), so `7.14.1-2` ships the same MIGraphX
build, and the payload gate below passes on it. That stage reproduces the
`7.14.1-1` render byte for byte from the `7.14.1-1` policy.

The earlier lane was the upstream `therock-7.13` release, rendered from a real
7.13 staged root. Its releases after `7.13.0-2` changed only MIGraphX:
`7.13.0-3` rebuilt it for protobuf 35.1, and `7.13.0-4` rebuilt it for
protobuf 36.1 and Abseil 20260817. The tooling from those rebuilds is part of
the 7.14.1 staging flow below. Build, deploy, and validation status belongs in
`docs/maintainers/current-state.md`.

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
   sha256-pinned Arch packages. It checks that prefix against the pinned
   sonames, runs the payload gate in
   [MIGraphX protobuf and Abseil rebuilds](#migraphx-protobuf-and-abseil-rebuilds),
   checks the staged Python import, and then renders this directory and
   previews the amerge plan. The build needs CPython 3.14 (`python-gfx1151`)
   as the active `python` and `python3.14-config`. The 2.16.1 payload in
   `7.14.1-1` was built against CPython 3.14.7, and `7.14.1-2` reuses it
   unchanged under CPython 3.14.8, whose patch release keeps the 3.14 ABI and
   the `libpython3.14.so.1.0` soname. MLIR stays off; see
   [the no-MLIR stubs](../../docs/patches.md#migraphx-therock-stage). The
   same section records the `rocm_add_version_resource` configure shim for
   the staged rocm-cmake 0.14.0.
4. Build the split family with `_THEROCK_ROOT=<stage>`.

`migraphx-gfx1151` gets its `libprotobuf.so=<ver>-64` depend from the staged
parser's `DT_NEEDED` through the policy's `soname_depends`, so the depend
follows the protobuf that MIGraphX was built against. The host has carried
protobuf 36.1 and Abseil 20260817, with the matching `libphonenumber` and
`python-protobuf`, since its 2026-10-02 full upgrade.

## MIGraphX protobuf and Abseil rebuilds

`migraphx-gfx1151` is the only package in this family that links protobuf and
Abseil. Its ONNX and TensorFlow parser libraries link `libprotobuf`,
`libutf8_validity`, and dozens of `libabsl_*` libraries directly, so an Arch
protobuf or Abseil soname change needs a pkgrel-only MIGraphX rebuild with
`tools/stage_migraphx_for_therock.zsh`:

- The script pins AMDMIGraphX to one commit (`--migraphx-ref`), so the rebuild
  changes only the linked ABI.
- The isolated prefix comes from the Arch `protobuf` and `abseil-cpp`
  archives, pinned by sha256. `--protobuf-dir` may name another prefix
  instead. Either way, the prefix's lib directory must hold both, CMake takes
  Abseil from its `cmake/absl`, and the script fails before building unless
  the prefix provides exactly the pinned `protobuf_soname`,
  `utf8_validity_soname`, and `libabsl_base.so.<abseil_soversion>`.
- Both parser libraries must link the pinned protobuf and `utf8_validity`
  sonames and `libabsl_*.so.<abseil_soversion>`. The script classifies the
  stage with the render's generator and policy, then reads `DT_NEEDED` from
  every regular file (not symlink) that the policy assigns to
  `migraphx-gfx1151` and that starts with the ELF magic, whatever its name.
  In 7.14.1-1 (AMDMIGraphX 2.16.1) those are 13 files: `flatc`,
  `migraphx-driver`, `migraphx-hiprtc-driver`, `libmigraphx_c`,
  `libmigraphx_py`, `libmigraphx_py_3.14`, the Python module, and the six
  `lib/migraphx/lib` libraries. (7.13.0-4 had 14, including
  `libIREECompiler.so`, which 7.14.1 dropped.) None may link a
  `libprotobuf.so*`, `libutf8_validity.so*`, or `libabsl_*` soname other than
  the pinned one; an older or newer one fails the stage, and so does a stage
  with fewer such ELFs than `migraphx_min_elfs` (13). The gate does not read
  the other sonames the `protobuf` package ships (`libprotobuf-lite`,
  `libprotoc`, `libutf8_range`).
- Pass `-j` explicitly; the script defaults to `nproc`. Package from the stage
  with `_THEROCK_ROOT=<stage> makepkg -Cf`. Every depend is declared per split
  package, which makepkg does not check, so the build host need not have the
  new protobuf or Abseil installed.

The package declares both libraries to pacman:

- `libprotobuf.so=<version>-64` matches the soname that Arch `protobuf`
  provides. The policy's `soname_depends` renders it from the staged ONNX
  parser's `DT_NEEDED`.
- Arch `abseil-cpp` provides no sonames, so the package declares
  `abseil-cpp>=20260817.0` and `abseil-cpp<20260818`. Abseil keeps one
  soversion (`2608.0.0` here) across an LTS's patch releases, so the range
  admits pkgrel rebuilds and `20260817.x` patches and blocks the next LTS.
  Without it, an Abseil-only update would leave MIGraphX linking libraries
  that no longer exist; Arch has already rebuilt protobuf against a new Abseil
  without changing its provides.
- Change the stage script's sonames and `abseil_soversion` together with the
  policy depends. `test_migraphx_depends_match_stage_script_sonames` checks
  that they agree.

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

## Kernel smoke and package checks

`tools/therock_kpack_smoke.py` launches at least one kernel per archive family
and fails a family that no probe reached or whose archive is missing:

| Probe | Archive | What runs |
| --- | --- | --- |
| `hip` | none | device enumeration; needs a `gfx1151` device |
| `rocrand` | `rand_lib` | XORWOW `generate_uniform` |
| `rocblas` | `blas_lib` | `sgemm` and `sscal` |
| `rocsolver` | `blas_lib` | `sgetrf` plus `sgetrs` |
| `rocfft` | none | FFT with runtime-compiled (RTC) kernels |
| `rocfft-callback` | `fft_lib` | FFT with a hipRTC load callback, so rocFFT loads its default store callback from the archive |
| `rccl` | `rccl_lib` | one-rank `PreMulSum` all-reduce, which needs a kernel, unlike a plain one-rank sum |
| `hiptensor` | `hiptensor_lib` | f32 permutation; the contraction is informational, since hipTensor returns `ARCH_MISMATCH` on gfx1151 |
| `rocalution` | `rocalution_lib` | 20 rounds of CSR SpMV and scale on the accelerator; compiles a tiny host C++ program, so it needs `c++` |
| `migraphx` (opt-in) | none | imports MIGraphX, parses a two-node ONNX model, and runs it on the `ref` and `gpu` targets; needs `numpy` and `onnx` |

Installed host:

```bash
python tools/therock_kpack_smoke.py probe --json <report.json>
```

Staged packages, rootless, before any install. Extract the built archives into
`<root>` with `bsdtar -xpf`, leaving out `.PKGINFO`, `.BUILDINFO`, `.MTREE`, and
`.INSTALL`, then:

```bash
python tools/therock_kpack_smoke.py check-packages --repo <repo-dir> --root <root>
python tools/therock_kpack_smoke.py probe --sandbox-root <root> --sandbox-python \
  --extra-lib-dir <protobuf-36.1-prefix>/usr/lib \
  --probe hip --probe rocrand --probe rocblas --probe rocsolver --probe rocfft \
  --probe rocfft-callback --probe rccl --probe hiptensor --probe rocalution --probe migraphx
```

`--sandbox-root` runs the probes in bubblewrap. The host filesystem is
read-only, `/dev/kfd` and `/dev/dri` pass through, `<root>/opt/rocm` replaces
`/opt/rocm`, and a directory under the workdir becomes a writable `/tmp`.
Without a writable `/tmp`, comgr cannot build the HIP blit kernels and every
handle that allocates device memory fails, which looks like a packaging fault.
`--sandbox-python` also replaces the host CPython with the staged one and keeps
the host site-packages. The extra library directory supplies protobuf 36.1 and
Abseil 20260817 to the MIGraphX parsers before the host has them.

With an empty directory bound over `/opt/rocm/.kpack`, every archive probe
fails and `hip` and `rocfft` still pass, so each archive probe depends on its
archive. That includes `rocfft-callback`, which then fails with an ordinary
`FAIL`, not the known-gap `XFAIL`.

`check-packages` fails when a path is in two packages (pacman would refuse the
transaction), when the extracted root and the package file lists differ, and
when a kpack-split library cannot reach its archive through its package's
declared depends. The last check reuses the generator's `KPACK_REF_UNOWNED`
check, but reads the built packages.

Known upstream gap: `rocfft-callback` aborts with `Cannot create GlobalVar
Obj for symbol: _ZL30store_cb_default_complex_float.static.<hash>`. The
`fft_lib` code object names rocFFT's static default callbacks with a
different `.static` hash than `librocfft` registers, so any rocFFT or hipFFT
plan that runs with a user callback aborts. Plans without callbacks are
unaffected. This is ROCm/TheRock#5444, which is closed upstream but still
present in the 7.14.1 dist tarball; the 7.13 flat payload passes the same
probe. The tool reports this failure signature as `XFAIL`, reports any other
failure of the probe as `FAIL`, and reports a pass as `XPASS` so the gap can be
retired.

Unresolved gap: on the 7.14.1 payload, rocALUTION CSR SpMV returns a wrong
result in a few percent of runs. In the bad runs only row 0 of the result is
written. Calling rocSPARSE `csrmv` directly on the same matrix, with or without
analysis, gave no wrong result in 300 runs. The `rocalution` probe runs 20
rounds. It reports `XFAIL` when some rounds are wrong and some right (the
`rocalution_lib` kernels load, but the results cannot be trusted), and `FAIL`
when every round is wrong or there is no accelerator. The root cause is not
isolated yet.

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

## RUNPATH and RPATH

The 7.14.1 payload has 27 objects whose RUNPATH names directories that do not
exist on the host: 22 objects in 11 packages carry CI build trees
(`/__w/rockrel/...`, sometimes with empty entries), and the five
`rocgdb-py3.10` to `rocgdb-py3.14` binaries carry the CI's
`/opt/python-shared/cp3xx-cp3xx/lib`. Three objects also miss a library they
NEED: `libamd_smi.so` (bundled libnl and libmnl) and `xmlwf` (bundled expat)
reach `lib/rocm_sysdeps/lib` only through CI paths, and
`llvm-omp-kernel-replay` has a clean RUNPATH that lacks
`lib/rocm_sysdeps/lib` for the bundled zlib and zstd.

Each affected package's `runpath_rewrites` sets the full RUNPATH with
`patchelf --set-rpath` at package time: the payload's `$ORIGIN` entries
without the foreign ones, or, where only CI entries existed, the `$ORIGIN`
path to the library's directory. `llvm-omp-kernel-replay` keeps its entries
and gains `$ORIGIN/../../rocm_sysdeps/lib`, which makes 28 rewritten objects.
`rocgdb-py3.14` then finds `libpython3.14.so.1.0` in `/usr/lib`; the 3.10 to
3.13 variants still need interpreters this stack does not ship.

The render fails any packaged ELF whose RUNPATH or RPATH, after rewrites,
leaves `/usr` and `/opt/rocm` (`FOREIGN_RUNPATH`), and every package function
ends with `_check_search_paths`, which applies the same rule to the packaged
files. See [the generator](../../docs/architecture/therock-generator.md#runpath-and-rpath).

`librocprofiler-sdk-tool` and `librocprofv3-list-avail` NEED
`librocprofiler-sdk-rocpd`, and the kokkosp tool library NEEDS
`librocprofiler-sdk-roctx`; neither component library NEEDS
`librocprofiler-sdk`. So `rocprofiler-sdk-gfx1151` depends on
`rocprofiler-sdk-rocpd-gfx1151` and `rocprofiler-sdk-roctx-gfx1151`, and they
no longer depend on it.

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
