# python-orjson-gfx1151

## Maintenance Snapshot

- Recipe package key: `rust_wheels`
- Scaffold template: `rust-wheel-pypi`
- Recipe build method: `cargo`
- Upstream repo: `https://github.com/ijl/orjson`
- Package version: `3.11.8`
- Recipe revision: `a1d7a68 (20260427, 16 patch commits)`
- Recipe steps: `31`
- Recipe dependencies: `cpython`
- Recorded reference packages: `extra/python-orjson, cachyos-extra-znver4/python-orjson`
- Authoritative reference package: `extra/python-orjson`
- Advisory reference packages: `cachyos-extra-znver4/python-orjson`
- Applied source patch files/actions: `1`

## Recipe notes

This package is the orjson output from the shared `rust_wheels` recipe phase.
That phase also documents cryptography, pydantic-core, tokenizers,
safetensors, and watchfiles as sibling Rust-wheel outputs, but those are not
dependencies of `python-orjson-gfx1151` unless listed in this package's
policy metadata.

orjson is built with Rust flags:
  RUSTFLAGS="-C target-cpu=znver5 -C opt-level=3"
This enables full AVX-512 + VAES codegen for Zen 5.

Do NOT add -C lto=thin here -- maturin adds -C embed-bitcode=no, which
conflicts with -C lto. Maturin manages its own LTO.

Rust's linker invokes `cc`, which resolves to the amdclang symlink, but AMD's
wrapper rejects binaries not prefixed with "amd". The package therefore sets:
CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=amdclang

Unset CFLAGS/CXXFLAGS/LDFLAGS during Rust builds because they contain
clang-specific flags (-famd-opt, -mllvm) that rustc's internal cc invocations
for build scripts do not understand.


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

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
