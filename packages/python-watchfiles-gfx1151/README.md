# python-watchfiles-gfx1151

## Maintenance Snapshot

- Recipe package key: `rust_wheels`
- Scaffold template: `rust-wheel-pypi`
- Recipe build method: `cargo`
- Upstream repo: `https://github.com/samuelcolvin/watchfiles`
- Package version: `1.1.1`
- Recipe revision: `a1d7a68 (20260427, 16 patch commits)`
- Recipe steps: `31`
- Recipe dependencies: `cpython`
- Recorded reference packages: `extra/python-watchfiles, cachyos-extra-znver4/python-watchfiles`
- Authoritative reference package: `extra/python-watchfiles`
- Advisory reference packages: `cachyos-extra-znver4/python-watchfiles`
- Applied source patch files/actions: `0`

## Recipe notes

This package is the watchfiles output from the shared `rust_wheels` recipe
phase. That phase also documents orjson, cryptography, pydantic-core,
tokenizers, and safetensors as sibling Rust-wheel outputs, but those are not
dependencies of `python-watchfiles-gfx1151` unless listed in this package's
policy metadata.

watchfiles supplies the Rust file-watching path used by ASGI reload and local
service workflows. The local package keeps that extension on the same znver5
Rust codegen lane as the rest of the optimized local wheel stack.


## Scaffold notes

- Part of the comprehensive Blackcat service/runtime wheel stack and consumed by the local vLLM package.
- Use the shared Rust-wheel renderer so Cargo, amdclang linker selection, path remapping, and Zen 5 flags stay aligned with the other Rust wheel packages.

## Intentional Divergences

- Follows Arch's python-watchfiles package shape while rebuilding the Rust extension through the Blackcat Rust-wheel compiler lane.
- Keeps ASGI reload and development-service file watching on the repo-owned optimized wheel stack.

## Update Notes

- Check Arch first for watchfiles release and any maturin/build-backend metadata changes before updating.
- After publishing a rebuilt package, verify `import watchfiles` and a minimal Python file-watch import path through the installed local Python lane.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
