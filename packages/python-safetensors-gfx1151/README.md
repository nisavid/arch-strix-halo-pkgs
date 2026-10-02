# python-safetensors-gfx1151

## Maintenance Snapshot

- Recipe package key: `rust_wheels`
- Scaffold template: `rust-wheel-pypi`
- Recipe build method: `cargo`
- Upstream repo: `https://github.com/huggingface/safetensors`
- Package version: `0.8.0`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `31`
- Recipe dependencies: `cpython`
- Recorded reference packages: `extra/python-safetensors, cachyos-extra-znver4/python-safetensors`
- Authoritative reference package: `extra/python-safetensors`
- Advisory reference packages: `cachyos-extra-znver4/python-safetensors`
- Applied source patch files/actions: `0`

## Recipe notes

safetensors is the model/checkpoint tensor I/O path for Transformers, vLLM,
and TorchAO validation. This package builds the Rust-backed Python extension
through the shared `rust_wheels` cargo path, keeping it on the same znver5
Rust codegen, linker, and path-remapping lane as the other local Rust-wheel
outputs.

After publishing a rebuilt package, verify `import safetensors` and a tiny
tensor save/load round trip through the installed local Python lane.


## Scaffold notes

- Part of the core Blackcat model/config stack and consumed by the local Transformers closure package.
- Use the shared Rust-wheel renderer so linker selection, path remapping, and znver5 codegen stay aligned with orjson and cryptography.

## Intentional Divergences

- Follows the Arch package shape while rebuilding the Rust extension through the recipe's znver5 Rust-wheel lane.
- Depends on the repo-owned NumPy lane because safetensors participates in model/checkpoint tensor I/O for the local inference stack.

## Update Notes

- Check Arch first for release and dependency metadata, then verify Transformers and TorchAO scenario compatibility before updating.
- After publishing a rebuilt package, verify `import safetensors` and a tiny tensor save/load round trip through the installed local Python lane.
- On 2026-09-22, update to safetensors 0.8.0 for the generation-C W2A closure (#110), built in the rootless C build root against TheRock 7.14.1 and python-gfx1151 3.14.7. Transformers 5.16.1 requires safetensors >=0.8.0.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
