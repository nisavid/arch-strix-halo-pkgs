# python-auto-round-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/intel/auto-round`
- Package version: `0.13.0`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `none`
- Authoritative reference package: `none`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Recipe notes

This package supplies AutoRound for llmcompressor's AutoRound modifier. It
ships Python quantization helpers and backend adapters; the current package
keeps upstream's wheel shape and points runtime dependencies at the local
gfx1151 torch, transformers, numpy, and accelerate stack.

The package follows the active PyPI auto-round lane because the local
llmcompressor package uses the dev dependency window and package-local metadata
patches for the repo-owned runtime stack. Keep updates tied to the active
quantization-tooling dependency window.


## Scaffold notes

- Part of the Blackcat Qwen3-VL quantization/tooling closure and consumed by llmcompressor.
- Use --skip-dependency-check because local torch, transformers, numpy, and accelerate packages satisfy upstream runtime requirements under gfx1151 package names.

## Intentional Divergences

- There is no current Arch-family auto-round package baseline, so this package is closure-first for llmcompressor's AutoRound modifier.
- Follows the active PyPI auto-round lane because the local llmcompressor package builds against the dev dependency window and carries metadata patches for the repo-owned runtime stack.

## Update Notes

- Check llmcompressor's AutoRound dependency bounds before updating.
- After publishing a rebuilt package, verify `import auto_round` and `from auto_round.schemes import PRESET_SCHEMES` through the installed local Python lane.
- On 2026-05-31, update to AutoRound 0.13.0 for the current PyPI source drift; keep deploy/install and installed import/API smokes as explicit gates.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
