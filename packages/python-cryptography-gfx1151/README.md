# python-cryptography-gfx1151

## Maintenance Snapshot

- Recipe package key: `rust_wheels`
- Scaffold template: `rust-wheel-pypi`
- Recipe build method: `cargo`
- Upstream repo: ``
- Package version: `46.0.7`
- Recipe revision: `ad42886 (20260317, 8 path commits)`
- Recipe steps: `30`
- Recipe dependencies: `cpython`
- Recorded reference packages: `extra/python-cryptography, cachyos-extra-znver4/python-cryptography`
- Authoritative reference package: `extra/python-cryptography`
- Advisory reference packages: `cachyos-extra-znver4/python-cryptography`
- Applied source patch files/actions: `0`

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

- This follows the recipe's Rust wheel build rules but still needs confirmation of the exact Arch build backend requirements on the current release.

## Intentional Divergences

- Follows the recipe's Rust-wheel compiler lane instead of the default distro compiler toolchain.
- Uses the optimized Python package as the interpreter baseline while otherwise tracking Arch's package shape closely.

## Update Notes

- Always confirm the current Arch build backend requirements before updating this package; cryptography regularly changes Rust/setuptools details.
- Treat any OpenSSL dependency drift in Arch as authoritative unless the recipe provides a concrete reason to diverge.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
