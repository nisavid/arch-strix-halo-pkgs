# python-pydantic-core-gfx1151

## Maintenance Snapshot

- Recipe package key: `rust_wheels`
- Scaffold template: `rust-wheel-pypi`
- Recipe build method: `cargo`
- Upstream repo: `https://github.com/pydantic/pydantic-core`
- Package version: `2.41.5`
- Recipe revision: `a1d7a68 (20260427, 16 commits touching recipe path)`
- Recipe steps: `31`
- Recipe dependencies: `cpython`
- Recorded reference packages: `extra/python-pydantic-core, cachyos-extra-znver4/python-pydantic-core`
- Authoritative reference package: `extra/python-pydantic-core`
- Advisory reference packages: `cachyos-extra-znver4/python-pydantic-core`
- Applied source patch files/actions: `0`

## Recipe notes

This package is the pydantic-core output from the shared `rust_wheels`
recipe phase. That phase also documents orjson, cryptography, tokenizers,
safetensors, and watchfiles as sibling Rust-wheel outputs, but those are not
dependencies of `python-pydantic-core-gfx1151` unless listed in this package's
policy metadata.

pydantic-core is deliberately kept on the Arch pydantic-compatible release
while it enters the local optimized stack. Move it to Blackcat's newer recipe
pin only with a matching local pydantic package or a validated compatibility
decision.

The Rust build follows the repo's shared Rust-wheel lane:
  RUSTFLAGS="-C target-cpu=znver5 -C opt-level=3"
and uses amdclang as the cargo linker through
CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER.


## Scaffold notes

- This is part of the core Blackcat model/config stack, but the package follows the current Arch pydantic-core ABI until the repo also owns python-pydantic.
- Use the shared Rust-wheel renderer so linker selection, path remapping, and znver5 codegen stay aligned with orjson and cryptography.

## Intentional Divergences

- Follows Arch's pydantic-core release while rebuilding the Rust extension through the recipe's znver5 Rust-wheel lane.
- Keeps pydantic-core aligned with the distro python-pydantic package until this repo carries a local python-pydantic package too.

## Update Notes

- Check Arch python-pydantic and python-pydantic-core together before updating; upstream pydantic normally constrains the pydantic-core ABI tightly.
- Do not adopt a newer pydantic-core release from recipe notes alone; keep pydantic-core aligned with the installed pydantic ABI unless this repo also carries and validates a matching pydantic package.
- After publishing a rebuilt package, verify `import pydantic_core` and a tiny `pydantic.BaseModel` validation through the installed local Python lane.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
