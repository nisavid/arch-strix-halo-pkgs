# python-safetensors-gfx1151

## Maintenance Snapshot

- Recipe package key: `rust_wheels`
- Scaffold template: `rust-wheel-pypi`
- Recipe build method: `cargo`
- Upstream repo: `https://github.com/huggingface/safetensors`
- Package version: `0.7.0`
- Recipe revision: `a1d7a68 (20260427, 16 patch commits)`
- Recipe steps: `31`
- Recipe dependencies: `cpython`
- Recorded reference packages: `extra/python-safetensors, cachyos-extra-znver4/python-safetensors`
- Authoritative reference package: `extra/python-safetensors`
- Advisory reference packages: `cachyos-extra-znver4/python-safetensors`
- Applied source patch files/actions: `0`

## Recipe notes

This package is the safetensors output from the shared `rust_wheels` recipe
phase. That phase also documents orjson, cryptography, pydantic-core,
tokenizers, and watchfiles as sibling Rust-wheel outputs, but those are not
dependencies of `python-safetensors-gfx1151` unless listed in this package's
policy metadata.

safetensors is the model/checkpoint tensor I/O path for Transformers, vLLM,
and TorchAO validation. The local package keeps that native extension on the
same znver5 Rust codegen lane as the rest of the optimized local wheel stack.


## Scaffold notes

- Part of the core Blackcat model/config stack and consumed by the local Transformers closure package.
- Use the shared Rust-wheel renderer so linker selection, path remapping, and znver5 codegen stay aligned with orjson and cryptography.

## Intentional Divergences

- Follows the Arch package shape while rebuilding the Rust extension through the recipe's znver5 Rust-wheel lane.
- Depends on the repo-owned NumPy lane because safetensors participates in model/checkpoint tensor I/O for the local inference stack.

## Update Notes

- Check Arch first for release and dependency metadata, then verify Transformers and TorchAO scenario compatibility before updating.
- After publishing a rebuilt package, verify `import safetensors` and a tiny tensor save/load round trip through the installed local Python lane.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
