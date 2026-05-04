# python-auto-round-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/intel/auto-round`
- Package version: `0.10.2`
- Recipe revision: `a1d7a68 (20260427, 16 path commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `none`
- Authoritative reference package: `none`
- Advisory reference packages: `none`
- Applied source patch files/actions: `1`

## Recipe notes

This package supplies AutoRound for llmcompressor's AutoRound modifier. It
ships Python quantization helpers and backend adapters; the current package
keeps upstream's wheel shape and points runtime dependencies at the local
gfx1151 torch, transformers, numpy, and accelerate stack.

The package uses auto-round 0.10.2 because llmcompressor 0.10.0.1 release
metadata accepts auto-round up to 0.10.2. Keep updates tied to the active
llmcompressor dependency window.


## Scaffold notes

- Part of the Blackcat Qwen3-VL quantization/tooling closure and consumed by llmcompressor.
- Use --skip-dependency-check because local torch, transformers, numpy, and accelerate packages satisfy upstream runtime requirements under gfx1151 package names.

## Intentional Divergences

- There is no current Arch-family auto-round package baseline, so this package is closure-first for llmcompressor's AutoRound modifier.
- Uses auto-round 0.10.2 because llmcompressor 0.10.0.1 release metadata caps auto-round at 0.10.2 even though newer PyPI releases exist.

## Update Notes

- Check llmcompressor's AutoRound dependency bounds before updating.
- After publishing a rebuilt package, verify `import auto_round` and `from auto_round.schemes import PRESET_SCHEMES` through the installed local Python lane.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
