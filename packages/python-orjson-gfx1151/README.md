# python-orjson-gfx1151

## Maintenance Snapshot

- Recipe package key: `rust_wheels`
- Scaffold template: `rust-wheel-pypi`
- Recipe build method: `cargo`
- Upstream repo: ``
- Package version: `3.11.8`
- Recipe revision: `b453c33 (20260422, 9 path commits)`
- Recipe steps: `30`
- Recipe dependencies: `cpython`
- Recorded reference packages: `extra/python-orjson, cachyos-extra-znver4/python-orjson`
- Authoritative reference package: `extra/python-orjson`
- Advisory reference packages: `cachyos-extra-znver4/python-orjson`
- Applied source patch files/actions: `1`

## Recipe notes

Builds and installs orjson and cryptography from source with Rust flags:
  RUSTFLAGS="-C target-cpu=znver5 -C opt-level=3"
This enables full AVX-512 + VAES codegen for Zen 5.

Do NOT add -C lto=thin here -- maturin adds -C embed-bitcode=no
which conflicts with -C lto. Maturin manages its own LTO.

Rust's linker invokes `cc` which resolves to the amdclang symlink,
but AMD's wrapper rejects binaries not prefixed with "amd". Fix:
CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=amdclang

Must unset CFLAGS/CXXFLAGS/LDFLAGS during Rust builds because
they contain clang-specific flags (-famd-opt, -mllvm) that rustc's
internal cc invocations for build scripts don't understand.

## Scaffold notes

- The recipe forces explicit Rust linker selection because AMD's cc wrapper rejects non-amd-prefixed frontend names.
- Keep RUSTFLAGS pinned to znver5 rather than native; the recipe documents a rustc native-detection issue on this platform.

## Intentional Divergences

- Uses the recipe's explicit Rust linker selection and path-remapping rules so AMD's toolchain wrappers behave correctly.
- Pins Rust target-cpu to znver5 instead of plain native because the recipe documents a rustc native-detection issue on this platform.
- Carries a build.rs capability probe patch so orjson enables the `cold_path` optimization only when rustc reports support for it.

## Update Notes

- Compare against Arch first for maturin/backend changes, then keep Cachy as a secondary reference for CPU-targeting differences.
- Retain CycloneDX/debug-path rewriting in package() unless upstream or Arch resolves the path leakage directly.
- Recheck `cold_path` feature detection when adopting a newer orjson or Rust lane.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
