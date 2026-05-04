# python-accelerate-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/huggingface/accelerate`
- Package version: `1.12.0`
- Recipe revision: `a1d7a68 (20260427, 16 patch commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `none`
- Authoritative reference package: `none`
- Advisory reference packages: `none`
- Applied source patch files/actions: `1`

## Recipe notes

This package supplies the Hugging Face accelerate dependency needed by the
Blackcat Qwen3-VL quantization/tooling follow-up lane. It is pure Python, but
it belongs in the local package closure because llmcompressor and AutoRound
expect a coherent installed accelerate package rather than an untracked venv
wheel.

The package uses accelerate 1.12.0 because llmcompressor 0.10.0.1 release
metadata accepts accelerate up to 1.12.0. Keep updates tied to the active
llmcompressor dependency window.


## Scaffold notes

- Part of the Blackcat Qwen3-VL quantization/tooling closure and consumed by llmcompressor and AutoRound.
- Use --skip-dependency-check because local torch, numpy, psutil, PyYAML, and safetensors packages satisfy upstream runtime requirements under gfx1151 package names.

## Intentional Divergences

- There is no current Arch-family accelerate package baseline, so this package is closure-first for llmcompressor and AutoRound tooling.
- Uses accelerate 1.12.0 because llmcompressor 0.10.0.1 release metadata caps accelerate at 1.12.0 even though newer PyPI releases exist.

## Update Notes

- Check llmcompressor and auto-round release metadata before updating; this package should stay inside the active quantization-tooling dependency bounds.
- After publishing a rebuilt package, verify `import accelerate` through the installed local Python lane.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
