# python-tokenizers-gfx1151

## Maintenance Snapshot

- Recipe package key: `rust_wheels`
- Scaffold template: `rust-wheel-pypi`
- Recipe build method: `cargo`
- Upstream repo: `https://github.com/huggingface/tokenizers`
- Package version: `0.23.3`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `31`
- Recipe dependencies: `cpython`
- Recorded reference packages: `cachyos/python-tokenizers`
- Authoritative reference package: `cachyos/python-tokenizers`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Recipe notes

This package is the tokenizers output from the shared `rust_wheels` recipe
phase. That phase also documents orjson, cryptography, pydantic-core,
safetensors, and watchfiles as sibling Rust-wheel outputs, but those are not
dependencies of `python-tokenizers-gfx1151` unless listed in this package's
policy metadata.

tokenizers is the Hugging Face tokenizer hot path for Transformers/vLLM
model loading. The local package keeps that native extension on the same
znver5 Rust codegen lane as the rest of the optimized local wheel stack.


## Scaffold notes

- Part of the core Blackcat model/config stack and consumed by the local Transformers closure package.
- Use the shared Rust-wheel renderer so linker selection, path remapping, and znver5 codegen stay aligned with orjson and cryptography.

## Intentional Divergences

- Uses the Blackcat Rust-wheel lane for a local Hugging Face tokenizer hot path instead of relying on the generic CachyOS wheel.
- There is no current Arch extra python-tokenizers package in the checked package databases as of 2026-05-01, so CachyOS is the practical Arch-family baseline.
- Declares the huggingface-hub range from the packaged metadata as versioned depends, python-huggingface-hub>=1:0.16.4 and python-huggingface-hub<1:3; the CachyOS baseline declares none. The published metadata makes huggingface-hub a hard requirement, and the compiled extension imports huggingface_hub when Tokenizer.from_pretrained is called, so pacman must keep it installed and inside the declared range. Arch packages huggingface-hub under epoch 1, so both bounds carry the epoch.

## Update Notes

- Check the current Hugging Face tokenizers release and Cachy package before updating; Transformers metadata can constrain this package.
- On 2026-05-01, reviewed PyPI tokenizers 0.23.1 but kept the package on 0.22.2 because Transformers 5.7.0 declares tokenizers<=0.23.0,>=0.22.0.
- After publishing a rebuilt package, verify `import tokenizers` and a tiny tokenizer construction through the installed local Python lane.
- On 2026-09-22, update to tokenizers 0.23.2 for the generation-C W2A closure (#110), built in the rootless C build root against TheRock 7.14.1 and python-gfx1151 3.14.7. Transformers 5.16.1 requires tokenizers >=0.23.1,<0.24.
- On 2026-10-10, update to tokenizers 0.23.3 for generation C's model closure move (#183). Its metadata requires huggingface-hub>=0.16.4,<3.0 where 0.23.2 required <2.0, so it is resolver-consistent with Arch's huggingface-hub 2.x. 0.23.3 also drops the truncation early exit present in 0.23.2, which restores every overflowing encoding. Transformers 5.18.0 requires tokenizers >=0.23.1,<0.24.
- When the packaged metadata changes its huggingface-hub range, change both versioned depends with it and keep the epoch.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
