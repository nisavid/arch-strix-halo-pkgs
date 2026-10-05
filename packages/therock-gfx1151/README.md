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

The official upstream `therock-7.13` release is the current package source
lane. This rendered package is built from a real 7.13 staged root. Releases
after `7.13.0-2` change only MIGraphX: `7.13.0-3` rebuilt it for protobuf 35.1,
and `7.13.0-4` rebuilds it for protobuf 36.1 and Abseil 20260817. Build,
deploy, and validation status belongs in `docs/maintainers/current-state.md`.

## MIGraphX protobuf and Abseil rebuilds

`migraphx-gfx1151` is the only package in this family that links protobuf and
Abseil. Its ONNX and TensorFlow parser libraries link `libprotobuf`,
`libutf8_validity`, and dozens of `libabsl_*` libraries directly, so an Arch
protobuf or Abseil soname change needs a pkgrel-only MIGraphX rebuild with
`tools/stage_migraphx_for_therock.zsh`:

- The script pins AMDMIGraphX to one commit (`--migraphx-ref`), so the rebuild
  changes only the linked ABI.
- `--protobuf-dir` points at an isolated prefix extracted from the Arch
  `protobuf` and `abseil-cpp` archives, checked against the sync DB sha256.
  The prefix's lib directory must hold both, and CMake takes Abseil from its
  `cmake/absl`.
- Both parser libraries must link the pinned protobuf and `utf8_validity`
  sonames and `libabsl_*.so.<abseil_soversion>`. The script classifies the
  stage with the render's generator and policy, then reads `DT_NEEDED` from
  every regular file (not symlink) that the policy assigns to
  `migraphx-gfx1151` and that starts with the ELF magic, whatever its name.
  In 7.13.0-4 those are 14 files, including `migraphx-driver`,
  `migraphx-hiprtc-driver`, `flatc`, `libIREECompiler.so`, `libmigraphx_c`,
  and the Python module. None may link another protobuf, `utf8_validity`, or
  Abseil soname; an older or newer one fails the stage, and so does a stage
  with fewer such ELFs than `migraphx_min_elfs` (14).
- The stage is a copy of the installed `/opt/rocm`, so it also holds the
  symlinks that `post_copy_commands` create. The policy's `ignore_globs`
  must cover them (`test_live_root_render_ignores_post_copy_symlinks`), and
  a render from the stage must reproduce the committed `PKGBUILD`, manifest,
  and filelists before packaging.
- Pass `-j` explicitly; the script defaults to `nproc`. Package from the stage
  with `_THEROCK_ROOT=<stage> makepkg -Cf`. Every depend is declared per split
  package, which makepkg does not check, so the build host need not have the
  new protobuf or Abseil installed.

The package declares both libraries to pacman:

- `libprotobuf.so=<version>-64` matches the soname that Arch `protobuf`
  provides.
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

The 7.14 package in the
[F protobuf and Abseil contract](../../docs/maintainers/c-build-root.md#f-protobuf-and-abseil-contract-108)
still declares no Abseil dependency.

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

## magma baseline

`magma-gfx1151` follows Arch `magma-hip` package metadata for its public
package interface while using the TheRock payload. It provides and replaces
both `magma-hip` and the legacy `hipmagma` name, and maps Arch's ROCm runtime
dependencies to the local gfx1151 split packages.
