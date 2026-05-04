# python-cryptography-gfx1151

## Maintenance Snapshot

- Recipe package key: `rust_wheels`
- Scaffold template: `rust-wheel-pypi`
- Recipe build method: `cargo`
- Upstream repo: `https://github.com/pyca/cryptography`
- Package version: `46.0.7`
- Recipe revision: `a1d7a68 (20260427, 16 patch commits)`
- Recipe steps: `31`
- Recipe dependencies: `cpython`
- Recorded reference packages: `extra/python-cryptography, cachyos-extra-znver4/python-cryptography`
- Authoritative reference package: `extra/python-cryptography`
- Advisory reference packages: `cachyos-extra-znver4/python-cryptography`
- Applied source patch files/actions: `0`

## Recipe notes

This package is the cryptography output from the shared `rust_wheels` recipe
phase. That phase also documents orjson, pydantic-core, tokenizers,
safetensors, and watchfiles as sibling Rust-wheel outputs, but those are not
dependencies of `python-cryptography-gfx1151` unless listed in this package's
policy metadata.

cryptography is built with Rust flags:
  RUSTFLAGS="-C target-cpu=znver5 -C opt-level=3"
This enables full AVX-512 + VAES codegen for Zen 5.

Do NOT add -C lto=thin here without a package-specific setuptools-rust
validation pass. The Arch-shaped cryptography build uses setuptools-rust
rather than maturin, so keep LTO policy tied to the declared backend and the
current upstream build-system metadata.

Rust's linker invokes `cc`, which resolves to the amdclang symlink, but AMD's
wrapper rejects binaries not prefixed with "amd". The package therefore sets:
CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=amdclang

Unset CFLAGS/CXXFLAGS/LDFLAGS during Rust builds because they contain
clang-specific flags (-famd-opt, -mllvm) that rustc's internal cc invocations
for build scripts do not understand.


## Scaffold notes

- This follows the recipe's Rust wheel build rules but still needs confirmation of the exact Arch build backend requirements on the current release.

## Intentional Divergences

- Follows the recipe's Rust-wheel compiler lane instead of the default distro compiler toolchain.
- Uses the optimized Python package as the interpreter baseline while otherwise tracking Arch's package shape closely.

## Update Notes

- Always confirm the current Arch build backend requirements before updating this package; cryptography regularly changes Rust/setuptools details.
- Treat any OpenSSL dependency drift in Arch as authoritative unless the recipe provides a concrete reason to diverge.
- On 2026-04-24, reviewed PyPI cryptography 47.0.0 while Arch's authoritative python-cryptography baseline remained 46.0.7-1. The runtime dependency shape stayed aligned for the local Python 3.14 path, but the sdist build-system requirement now excludes maturin 1.12.0.
- On 2026-04-25, Arch adopted python-cryptography 47.0.0-1 with python-maturin, clang, lld, llvm, python-setuptools, and python-wheel makedepends. Keep the local package on 46.0.7 until a package-specific build refresh validates the newer maturin lane.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
