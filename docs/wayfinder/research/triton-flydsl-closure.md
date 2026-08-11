# Triton and FlyDSL Source Closure

Status as of 2026-08-11.

This is a source, packaging, and compatibility research artifact for the
`gfx1151` inference stack. It resolves the source-closure questions raised by
[issue 76](https://github.com/nisavid/arch-strix-halo-pkgs/issues/76) and
[issue 78](https://github.com/nisavid/arch-strix-halo-pkgs/issues/78) without
implementing packages, changing package policy, building, deploying,
installing, or claiming live validation.

## Decision

FlyDSL is no longer blocked on missing public source or a necessarily
wheel-only distribution. AITER `v0.1.19.post2` pins `flydsl==0.3.0`, and ROCm
publishes that exact version as an Apache-2.0 source tag at commit
`5675194f18f0655ce1f979c517f673533963fa93`. The tagged source carries its
LLVM revision, submodules, build scripts, and embedded MLIR Python runtime.
The viable package shape is therefore a standalone source-built
`python-flydsl-gfx1151` package at that exact AITER-selected tag.

Triton source closure also exists, but one final version choice is coupled to
the PyTorch refresh:

- For a stack that remains on the Triton 3.7 family, replace stale ROCm
  `main_perf` commit `0ec280cf80dd91e9a86887981a670f2d4541a32b` with ROCm
  `release/internal/3.7.x` commit
  `532137f0a698ecde89e5e4782987e94c40fe5b30`. It reports 3.7.1, carries the
  current ROCm release-specific AMD fixes, and matches AITER's first-party
  3.7 installer lane.
- If the stack adopts ROCm/PyTorch `release/2.13`, Triton must instead follow
  PyTorch's exact ROCm Triton 3.8.0 pin,
  `4cff872ced001ea92d9fcf05b3f6517e2b486d19`. AITER should then build with
  `AITER_USE_SYSTEM_TRITON=1`; its Triton and Gluon consumers need explicit
  compatibility validation because AITER itself currently installs and tests
  Triton 3.7.0, not 3.8.0.

Do not implement an independently chosen Triton version before the PyTorch
source lane is fixed. The two first-party consumers have not yet converged on
one release: current AITER selects 3.7.0 while current ROCm/PyTorch 2.13 selects
3.8.0. AITER's lower-bound check of Triton 3.6 is not compatibility proof.

## AITER Dependency Contract

The latest formal AITER release is
[v0.1.19](https://github.com/ROCm/aiter/releases/tag/v0.1.19). The subsequent
source tag
[v0.1.19.post2](https://github.com/ROCm/aiter/tree/a63ede724b153564f3ed3fc538055fd15178c77d),
commit `a63ede724b153564f3ed3fc538055fd15178c77d`, is the useful refresh input:
it contains the 0.3.0 FlyDSL dependency bump and Python 3.14 Gluon compatibility
work visible in the
[v0.1.19...v0.1.19.post2 comparison](https://github.com/ROCm/aiter/compare/v0.1.19...v0.1.19.post2).

At that exact source ref:

- [`setup.py`](https://github.com/ROCm/aiter/blob/a63ede724b153564f3ed3fc538055fd15178c77d/setup.py)
  defines `FLYDSL_VERSION = "flydsl==0.3.0"`, supports
  `AITER_USE_SYSTEM_TRITON=1`, and leaves FlyDSL AOT prebuild disabled by
  default through `PREBUILD_KERNELS=0`.
- [`requirements.txt`](https://github.com/ROCm/aiter/blob/a63ede724b153564f3ed3fc538055fd15178c77d/requirements.txt)
  also pins `flydsl==0.3.0`, so the package is a runtime dependency rather than
  merely an optional build helper.
- The first-party
  [`install_triton.sh`](https://github.com/ROCm/aiter/blob/a63ede724b153564f3ed3fc538055fd15178c77d/.github/scripts/install_triton.sh)
  installs AMD-index `triton==3.7.0` and `triton-kernels==1.0.0`; its installed
  check rejects only versions below 3.6.0.

Package AITER without allowing its setup logic to fetch or replace dependency
wheels. The expected source-package integration is FlyDSL from the separately
verified source package, one system Triton chosen with PyTorch, and
`AITER_USE_SYSTEM_TRITON=1`. Start with `PREBUILD_KERNELS=0`; enabling FlyDSL
AOT is a later package and validation decision, not part of source closure.

The presence of FlyDSL and Gluon kernels in AITER source does not prove those
kernels work on `gfx1151`. Upstream release assets and CI do not provide a
`gfx1151` acceptance result. The existing package's local patches and tracked
runtime gaps therefore remain implementation-time review inputs.

## FlyDSL Source Closure

ROCm now publishes FlyDSL in the public
[`ROCm/FlyDSL`](https://github.com/ROCm/FlyDSL) repository. Release
[v0.3.0](https://github.com/ROCm/FlyDSL/releases/tag/v0.3.0), commit
`5675194f18f0655ce1f979c517f673533963fa93`, is the correct candidate because
it is the exact version required by AITER `v0.1.19.post2`. A newer v0.3.1 tag
exists, but the
[v0.3.0...v0.3.1 comparison](https://github.com/ROCm/FlyDSL/compare/v0.3.0...v0.3.1)
includes LLVM/API movement and additional RDNA work; do not substitute it
without separately changing and validating AITER's dependency contract.

The v0.3.0 source is sufficient for an auditable source package:

- The tagged [`LICENSE`](https://github.com/ROCm/FlyDSL/blob/5675194f18f0655ce1f979c517f673533963fa93/LICENSE)
  is Apache-2.0.
- The tagged [`README`](https://github.com/ROCm/FlyDSL/blob/5675194f18f0655ce1f979c517f673533963fa93/README.md)
  documents source builds against either a built LLVM/MLIR tree or an
  explicit `MLIR_PATH`.
- [`thirdparty/llvm-hash.txt`](https://github.com/ROCm/FlyDSL/blob/5675194f18f0655ce1f979c517f673533963fa93/thirdparty/llvm-hash.txt)
  pins upstream LLVM commit
  `7f77ca0dbda4abbf9af06537b2c475f20ccd6007`; the tagged
  [`scripts/build_llvm.sh`](https://github.com/ROCm/FlyDSL/blob/5675194f18f0655ce1f979c517f673533963fa93/scripts/build_llvm.sh)
  defines the LLVM/MLIR build shape.
- The source tag records DLPack commit
  `84d107bf416c6bab9ae68ad285876600d230490d` and TVM-FFI commit
  `ed067c17b259774f4ddc23ba7de937a90642bbb1` as gitlinks. Fetch the tag
  recursively and verify those inputs rather than relying on a floating
  checkout.
- [`python/mlir_flydsl/CMakeLists.txt`](https://github.com/ROCm/FlyDSL/blob/5675194f18f0655ce1f979c517f673533963fa93/python/mlir_flydsl/CMakeLists.txt)
  builds the embedded MLIR Python runtime and applies symbol-hiding for LLVM
  symbols to avoid collisions with ROCm libraries such as `libamd_comgr.so`.

The public PyPI artifacts are not the package source. Their absence of an
sdist does not matter now that a licensed, tagged, recursively pin-able source
tree exists.

### LLVM boundary

The committed TheRock 7.13 package file list at
`packages/therock-gfx1151/filelists/rocm-llvm-gfx1151.txt` contains MLIR CMake
metadata, headers, libraries, and tools, including `MLIRConfig.cmake`,
`AddMLIRPython.cmake`, `libMLIR.so`, and `mlir-opt`. The old statement that the
current `rocm-llvm-gfx1151` payload has no usable MLIR development surface is
therefore obsolete as a source-availability blocker.

That does not establish ABI or MLIR API compatibility. TheRock
[`therock-7.13`](https://github.com/ROCm/TheRock/tree/therock-7.13) pins ROCm
LLVM commit
[`43215c73116c407735c85a180d174f718798c328`](https://github.com/ROCm/llvm-project/commit/43215c73116c407735c85a180d174f718798c328),
which has diverged from FlyDSL's upstream LLVM pin. TheRock
[`therock-7.14`](https://github.com/ROCm/TheRock/tree/therock-7.14) pins
[`46fcb339fb61119b337f973c7ca9e710a319fdd0`](https://github.com/ROCm/llvm-project/commit/46fcb339fb61119b337f973c7ca9e710a319fdd0);
that history contains the FlyDSL v0.3.0 LLVM pin but is much newer. Ancestry
is not a compatibility guarantee for MLIR's changing C++ and Python build
APIs.

The low-risk initial closure is to build FlyDSL with its exact pinned sidecar
LLVM/MLIR and package the embedded runtime that upstream designed. Reusing a
TheRock LLVM/MLIR installation is an optional later optimization, gated on a
successful compile, link audit, import, and kernel smoke. Do not silently set
`MLIR_PATH` to whichever system installation is present.

## Triton Source Closure

The current `python-triton-gfx1151` source pin is not viable for a refresh.
ROCm `main_perf` remains at `0ec280cf80dd91e9a86887981a670f2d4541a32b` and the
package reports `3.0.0+git0ec280cf`; its local Python 3.14/pybind11,
`-Werror`, and `AttrsDescriptor.__repr__` patches all require a fresh rebase or
drop audit against the selected source.

For the 3.7 family, use ROCm commit
[`532137f0a698ecde89e5e4782987e94c40fe5b30`](https://github.com/ROCm/triton/commit/532137f0a698ecde89e5e4782987e94c40fe5b30)
from `release/internal/3.7.x`. Its
[`setup.py`](https://github.com/ROCm/triton/blob/532137f0a698ecde89e5e4782987e94c40fe5b30/setup.py)
reports 3.7.1. Relative to upstream
[`v3.7.1`](https://github.com/triton-lang/triton/releases/tag/v3.7.1), the
[exact comparison](https://github.com/ROCm/triton/compare/f797708c0626e5f9840ca5b0a98790e2c7cb09ad...532137f0a698ecde89e5e4782987e94c40fe5b30)
shows the current ROCm release-specific commits, including AMD descriptor-load
and async-copy fixes. This is a better AMD source lane than the stale
`main_perf` branch.

Triton must keep an exact compatible LLVM sidecar. The 3.7 source pins LLVM
commit `1f126a6dea50d185c0781743a667390037ae88bd` in
[`cmake/llvm-hash.txt`](https://github.com/ROCm/triton/blob/532137f0a698ecde89e5e4782987e94c40fe5b30/cmake/llvm-hash.txt),
and the tagged
[`README`](https://github.com/ROCm/triton/blob/532137f0a698ecde89e5e4782987e94c40fe5b30/README.md)
warns that LLVM has no stable API while documenting `LLVM_SYSPATH` for a custom
build. Do not redirect this build to TheRock LLVM merely because both provide
LLVM and MLIR files.

ROCm/PyTorch creates the coupled alternative. Current `release/2.13` commit
`4be323cffdd92aeb272b15958ebafe9a5e6c6a33` pins ROCm Triton commit
`4cff872ced001ea92d9fcf05b3f6517e2b486d19` in
[`triton.txt`](https://github.com/ROCm/pytorch/blob/4be323cffdd92aeb272b15958ebafe9a5e6c6a33/.ci/docker/ci_commit_pins/triton.txt)
and declares version 3.8.0 in
[`triton_version.txt`](https://github.com/ROCm/pytorch/blob/4be323cffdd92aeb272b15958ebafe9a5e6c6a33/.ci/docker/triton_version.txt).
If that PyTorch lane is adopted, its exact Triton pin is the candidate for the
shared system package; the AITER 3.7 selection becomes a compatibility test,
not a reason to install a second runtime Triton.

The 3.8 source records its LLVM inputs and artifact checksums in
[`cmake/llvm-info.json`](https://github.com/ROCm/triton/blob/4cff872ced001ea92d9fcf05b3f6517e2b486d19/cmake/llvm-info.json)
and related build metadata in
[`cmake/llvm-build-info.json`](https://github.com/ROCm/triton/blob/4cff872ced001ea92d9fcf05b3f6517e2b486d19/cmake/llvm-build-info.json).
An implementation must reconcile and pin that exact source-build closure; it
must not substitute TheRock LLVM or download an unverified prebuilt toolchain.

## Recommended Package Order

1. Fix the PyTorch refresh lane. If it adopts ROCm/PyTorch 2.13, select its
   exact 3.8.0 Triton pin. Otherwise select ROCm Triton internal 3.7.1 for the
   current AITER-compatible lane.
2. Implement `python-triton-gfx1151` from the selected exact commit with its
   exact compatible LLVM source closure. Rebase or drop every existing local
   patch by demonstrated need.
3. Implement `python-flydsl-gfx1151` from FlyDSL v0.3.0, recursively pinned,
   initially using FlyDSL's exact sidecar LLVM/MLIR and embedded Python
   runtime.
4. Refresh `python-amd-aiter-gfx1151` to `v0.1.19.post2` with network-managed
   dependency installation disabled, the packaged FlyDSL dependency, the
   selected system Triton, `AITER_USE_SYSTEM_TRITON=1`, and initially
   `PREBUILD_KERNELS=0`.
5. Consider FlyDSL AOT and TheRock-LLVM reuse only after the basic source
   packages and installed runtime path pass their gates.

## Required Validation Gates

No gate below was run for this research artifact.

Source and package gates:

- verify every selected commit, archive checksum, license, and recursive
  submodule/gitlink; prove packaging performs no dependency or toolchain
  network fetch
- build Triton with its selected exact LLVM closure and verify its version,
  provides metadata, AMD backend payload, and `gfx1151` code-generation target
- build FlyDSL v0.3.0 with its exact LLVM/MLIR closure; audit the installed
  embedded MLIR payload, RPATH/linkage, and exported symbols for unintended
  system or ROCm LLVM binding
- build AITER against the packaged FlyDSL and selected system Triton, with its
  automatic Triton installation disabled; run bounded package-local tests

Installed smoke gates:

- import FlyDSL without undeclared paths and run a minimal compile/JIT smoke on
  `gfx1151`
- import Triton, select the AMD device, and run a bounded kernel plus an
  Inductor compile smoke
- import AITER and execute representative Triton and Gluon/FlyDSL kernels on
  `gfx1151`; if Triton 3.8 is selected, cover each AITER surface that upstream
  currently tests with 3.7
- inspect loaded shared objects so sidecar LLVM/MLIR libraries do not collide
  with TheRock ROCm libraries

Affected live-scenario gates:

- rerun the tracked PyTorch/Inductor, AITER, AOTriton, FlashAttention Triton
  AMD, vLLM, and any FlyDSL/Gluon consumer scenarios selected by the package
  diff
- keep source updated, package built, deployed/installed, installed-smoked,
  and live-scenario validated states separate in the closeout
- preserve existing expected failures until a rerun proves they are resolved;
  this source research resolves no host or `gfx1151` runtime failure

## Source Disposition

All sources were retrieved on 2026-08-11. `source-verified` means the cited
source supports the packaging or compatibility fact; it does not mean a local
package or runtime was validated.

| Source | Type | Status | Disposition |
| --- | --- | --- | --- |
| [AITER v0.1.19.post2 source](https://github.com/ROCm/aiter/tree/a63ede724b153564f3ed3fc538055fd15178c77d) | first-party tagged source | `source-verified` | Adopt as the AITER refresh research pin; package implementation and `gfx1151` validation remain open. |
| [AITER Triton installer](https://github.com/ROCm/aiter/blob/a63ede724b153564f3ed3fc538055fd15178c77d/.github/scripts/install_triton.sh) | first-party build/CI script | `source-verified` | Treat Triton 3.7.0 as AITER's tested selection, not permission for package-time wheel installation. |
| [FlyDSL v0.3.0 release](https://github.com/ROCm/FlyDSL/releases/tag/v0.3.0) | first-party release and tagged source | `source-verified` | Adopt as the exact standalone source-package candidate required by AITER. |
| [FlyDSL LLVM pin](https://github.com/ROCm/FlyDSL/blob/5675194f18f0655ce1f979c517f673533963fa93/thirdparty/llvm-hash.txt) | first-party build metadata | `source-verified` | Use for the initial exact sidecar LLVM/MLIR build closure. |
| [ROCm Triton internal 3.7.1](https://github.com/ROCm/triton/commit/532137f0a698ecde89e5e4782987e94c40fe5b30) | first-party source commit | `source-verified` | Adopt only for a 3.7-family stack; supersedes stale `main_perf` as the package candidate. |
| [ROCm/PyTorch 2.13 Triton pin](https://github.com/ROCm/pytorch/blob/4be323cffdd92aeb272b15958ebafe9a5e6c6a33/.ci/docker/ci_commit_pins/triton.txt) | first-party integration pin | `source-verified` | If PyTorch 2.13 is adopted, use its exact ROCm Triton 3.8.0 commit as the shared runtime candidate. |
| [TheRock 7.13 ROCm LLVM pin](https://github.com/ROCm/llvm-project/commit/43215c73116c407735c85a180d174f718798c328) | first-party release source pointer | `source-verified` | The local split payload has an MLIR SDK, but the version is not the FlyDSL pin; compatibility is unvalidated. |
| [TheRock 7.14 ROCm LLVM pin](https://github.com/ROCm/llvm-project/commit/46fcb339fb61119b337f973c7ca9e710a319fdd0) | first-party release source pointer | `source-verified` | Contains the FlyDSL LLVM pin in its history, but direct FlyDSL use remains `advisory-only` until built and tested. |

## Closure

Retire the missing-source and missing-MLIR-payload blockers. Keep two explicit
implementation gates: select Triton with the PyTorch lane, then prove AITER
compatibility with that one system Triton. FlyDSL v0.3.0 and both candidate
Triton source lanes have auditable first-party source closure; none has yet
been built or validated by this research task on `gfx1151`.
