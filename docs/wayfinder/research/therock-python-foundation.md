# TheRock and Python foundation boundary

Research date: 2026-08-11

Ticket: [#84](https://github.com/nisavid/arch-strix-halo-pkgs/issues/84)

## Decision

Treat TheRock 7.14, CPython 3.14.7, and MIGraphX 2.16 as one coordinated
foundation lane, but not as one indivisible rebuild. Establish CPython 3.14.7
first, stage the complete TheRock 7.14 `gfx1151` payload, then build MIGraphX
2.16 once against the final ROCm, Protobuf 35.1, Abseil 20260526, and Python
3.14 inputs. Render the split packages from that combined staged root before
rebuilding downstream inference packages.

The existing Python 3.14.6 to 3.14.7 patch update does not, by itself, require
a mass native-extension rebuild. The TheRock and MIGraphX migrations do require
new artifacts, and the Protobuf and Abseil transitions make a MIGraphX parser
rebuild mandatory.

## Current and target boundary

| Surface | Repository baseline | Evidence-backed target | Boundary consequence |
| --- | --- | --- | --- |
| CPython | `python-gfx1151` 3.14.6-1 ([recipe](../../../packages/python-gfx1151/recipe.json), [PKGBUILD](../../../packages/python-gfx1151/PKGBUILD)) | CPython 3.14.7, released 2026-08-05 ([release](https://www.python.org/downloads/release/python-3147/)); compare with Arch `core-testing` 3.14.7-1 ([package](https://archlinux.org/packages/core-testing/x86_64/python/)) | Update the interpreter first. Preserve Arch's package integration shape and the repository's amdclang/PGO/LTO policy. |
| TheRock | 7.13.0-2 ([policy](../../../policies/therock-packages.toml)) | TheRock 7.14.0 at tag commit `418cd5f63abb7a604bad5874cd7b2e29334e640f` ([release](https://github.com/ROCm/TheRock/releases/tag/therock-7.14), [version](https://github.com/ROCm/TheRock/blob/therock-7.14/version.json)); AMD publishes a `gfx1151` distribution archive ([index](https://repo.amd.com/rocm/tarball-multi-arch/)) | Stage the real 7.14 archive and rerender the full split output. Do not treat this as a `pkgrel`-only repackage or mix 7.13 and 7.14 payloads. |
| Protobuf and Abseil | MIGraphX currently declares `libprotobuf.so=35.0.0-64` ([policy](../../../policies/therock-packages.toml)) | Arch Protobuf 35.1-1 ([package](https://archlinux.org/packages/extra/x86_64/protobuf/)) and Abseil 20260526.0-2 ([package](https://archlinux.org/packages/extra/x86_64/abseil-cpp/)) | Rebuild direct native consumers. The migration must reject stale Protobuf 35.0 or 34 dependencies in staged parser libraries. |
| MIGraphX | A separately staged MIGraphX payload is owned by the TheRock split policy ([staging tool](../../../tools/stage_migraphx_for_therock.zsh)) | AMDMIGraphX `rocm-7.14`, version 2.16.0, commit `4bcfe75b225e4e0b9387fe14645cb1c7216e6742` ([release](https://github.com/ROCm/AMDMIGraphX/releases/tag/rocm-7.14), [CMake version](https://github.com/ROCm/AMDMIGraphX/blob/rocm-7.14/CMakeLists.txt)) | Build it once after every foundation input is final, then include it in the staged split-package root. |

The repository's Python policy already permits adopting a reviewed CPython
3.14 patch release without waiting for Arch or CachyOS. Arch stable remains at
3.14.6-1 while `core-testing` has 3.14.7-1
([stable](https://archlinux.org/packages/core/x86_64/python/),
[testing](https://archlinux.org/packages/core-testing/x86_64/python/)); CachyOS
is also still on a 3.14.6 package
([package](https://packages.cachyos.org/package/cachyos-v4/x86_64_v4/python)).
Use Arch testing as the current integration reference and CachyOS only as an
advisory optimization reference until it catches up.

## Compatibility constraints

### TheRock 7.14 is a payload migration

ROCm 7.14 is the first release built entirely through TheRock
([ROCm overview](https://rocm.docs.amd.com/en/docs-7.14.0/about/what-is-rocm.html)).
AMD describes the 7.14 Core SDK as API- and ABI-compatible with legacy ROCm 7.2,
but also documents new package names, filesystem layout changes, and the move of
MIGraphX to ROCm-Extras
([transition guide](https://rocm.docs.amd.com/en/docs-7.14.0/about/transition-guide-TheRock.html)).
That compatibility statement means an external 7.2 application need not be
rebuilt solely because of the Core SDK ABI. It does not make the repository's
generated 7.13 split payload interchangeable with 7.14.

The upstream 7.13-to-7.14 range contains hundreds of changes and significant
release-workflow and output-shape work
([comparison](https://github.com/ROCm/TheRock/compare/therock-7.13...therock-7.14)).
TheRock reports `gfx1151` Linux builds and sanity tests, but does not mark it
release-ready, and explicitly warns that TheRock remains under active
development
([supported GPUs](https://github.com/ROCm/TheRock/blob/therock-7.14/SUPPORTED_GPUS.md)).
The published archive is therefore a viable source input, not sufficient
runtime validation.

### CPython 3.14.7 preserves the 3.14 ABI boundary

CPython documents forward and backward ABI compatibility within a minor
release when builds use compatible platform and compiler options. It also
warns that private underscore-prefixed APIs can change in patch releases
([C API stability](https://docs.python.org/3.14/c-api/stable.html)). Therefore:

- Do not schedule an ecosystem-wide native-extension rebuild solely for
  3.14.6 to 3.14.7.
- Build new TheRock and MIGraphX Python extensions against 3.14.7 because those
  artifacts are changing anyway.
- Smoke every packaged native import after interpreter cutover and rebuild any
  extension that uses private APIs or fails to load.

The scale of Arch's completed Python 3.14 rebuild demonstrates the different
boundary at a minor-version transition: 2,734 packages were rebuilt for 3.14
([Arch rebuild](https://archlinux.org/todo/python-314-rebuild/)). That evidence
does not apply to a 3.14 patch release.

### Protobuf and Abseil force the MIGraphX parser rebuild

Protobuf v35.1 reports release version 7.35.1 while its CMake project version is
35.1.0
([release](https://github.com/protocolbuffers/protobuf/releases/tag/v35.1),
[CMake](https://github.com/protocolbuffers/protobuf/blob/v35.1/CMakeLists.txt)).
Its shared `libprotobuf` publishes Abseil and `utf8_validity` through its link
interface
([target](https://github.com/protocolbuffers/protobuf/blob/v35.1/cmake/libprotobuf.cmake),
[Abseil integration](https://github.com/protocolbuffers/protobuf/blob/v35.1/cmake/abseil-cpp.cmake)).

MIGraphX's ONNX and TensorFlow parser targets both find and link
`protobuf::libprotobuf`
([ONNX target](https://github.com/ROCm/AMDMIGraphX/blob/rocm-7.14/src/onnx/CMakeLists.txt),
[TensorFlow target](https://github.com/ROCm/AMDMIGraphX/blob/rocm-7.14/src/tf/CMakeLists.txt)).
Its Python target is separately built for each selected interpreter version and
links that interpreter's runtime
([Python target](https://github.com/ROCm/AMDMIGraphX/blob/rocm-7.14/src/py/CMakeLists.txt)).
Arch consequently included MIGraphX in both its Protobuf 35.1 and Abseil
20260526 rebuild sets
([Protobuf rebuild](https://archlinux.org/todo/protobuf-351-grpc-1810/),
[Abseil rebuild](https://archlinux.org/todo/abseil-cpp-202605260-grpc-1810/)).
This is a hard native rebuild boundary, not a packaging-metadata-only change.

## Rebuild and validation matrix

| Layer | Rebuild expectation | Required evidence before advancing |
| --- | --- | --- |
| `python-gfx1151` | Build 3.14.7 as the new interpreter base. No automatic rebuild of every 3.14 extension. | Package build; feature parity including PEP 668, SQLite, Tk, and sanitized build paths; installed native-import smoke. |
| TheRock split family | Restage and rerender every split package from the 7.14 `gfx1151` archive plus locally built MIGraphX. | Complete manifest ownership; no collisions or private paths; package builds; installed core runtime, device enumeration, BLAS, and Python-tool smokes. |
| `migraphx-gfx1151` | Build AMDMIGraphX 2.16 once against TheRock 7.14, Protobuf 35.1, Abseil 20260526, and CPython 3.14.7. | ONNX and TensorFlow parser `DT_NEEDED` entries resolve only to current Protobuf/Abseil/utf8 libraries; Python 3.14 import; parser smoke; installed MIGraphX runtime smoke. |
| Native downstream ROCm packages | Rebuild packages whose sources or native outputs consume the changed ROCm toolchain, headers, libraries, or Python binding surface. | Package-local imports and runtime smokes, followed by the repository's live inference scenarios. |
| Pure-Python dependents | Do not rebuild merely for the 3.14.7 patch. Rebuild only for package-policy or test failures. | Import and contract checks against the installed interpreter and foundation. |

AMD's own 7.14 validation matrix lists MIGraphX 2.16 for `gfx942` and `gfx950`
with Python 3.12, not `gfx1151` with Python 3.14
([ROCm 7.14 release notes](https://rocm.docs.amd.com/en/docs-7.14.0/about/release-notes.html)).
Repository-specific installed and live inference scenarios remain required;
upstream release status cannot close that gap.

## Recommended migration sequence

1. Resolve any pending 7.13 Protobuf 35.1 repair independently as a
   current-state fix. Do not fold that repair's provenance into the 7.14 source
   migration.
2. Pin immutable inputs: CPython 3.14.7 source, TheRock 7.14 tag and `gfx1151`
   archive, AMDMIGraphX `rocm-7.14`, Protobuf 35.1, and Abseil 20260526.
3. Build and validate `python-gfx1151` 3.14.7.
4. Stage the complete TheRock 7.14 `gfx1151` distribution.
5. Build MIGraphX 2.16 once against the final interpreter and native dependency
   set, then add that payload to the staged TheRock root.
6. Rerender and audit the entire split-package family. Reject mixed 7.13/7.14
   ownership and stale Protobuf 35.0 or 34 parser dependencies.
7. Build, install, and smoke the foundation as distinct gates. Only then start
   downstream rebuild waves and live inference validation.

This sequence avoids two unnecessary cycles: rebuilding MIGraphX first for
Python 3.14.6 and again for 3.14.7, or rebuilding all Python extensions merely
because of a patch-level interpreter update.
