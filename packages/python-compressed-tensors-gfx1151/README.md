# python-compressed-tensors-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/vllm-project/compressed-tensors`
- Package version: `0.15.0.1`
- Recipe revision: `a1d7a68 (20260427, 16 patch commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `none`
- Authoritative reference package: `none`
- Advisory reference packages: `none`
- Applied source patch files/actions: `1`

## Recipe notes

This package is the compressed-tensors output for the Blackcat Qwen3-VL
tooling follow-up lane. Blackcat's quantization helper names
llmcompressor 0.10.0.1 and compressed-tensors 0.14.0.1, but the installed
vLLM 0.20.1 lane expects compressed-tensors 0.15.0.1. Keep this package
aligned with vLLM first, then reconcile llmcompressor as a separate package
closure.

The package is pure Python today, but it still belongs in the local package
set because vLLM compressed-tensors quantization and Qwen3-VL W8A8/W8A16
checkpoint loading need a coherent installed dependency rather than an
untracked venv wheel.

The upstream sdist pins `setuptools_scm==8.2.0` as a build dependency, while
the host has a newer Arch `python-setuptools-scm`. The package skips Python
build dependency checking and uses the system build backend because this is a
pure-Python wheel and the newer backend builds the same installed package
shape.


## Scaffold notes

- Part of the Blackcat Qwen3-VL quantization/tooling follow-up lane.
- Keep this package aligned with the installed vLLM compressed-tensors requirement before promoting Qwen3-VL compressed-tensors scenarios.
- Uses --skip-dependency-check to avoid the stale exact setuptools_scm build pin in the PyPI sdist.
- Keep llmcompressor out of this package's validation claim until its older dependency pins are reconciled with the local torch and transformers stack.

## Intentional Divergences

- There is no current Arch-family compressed-tensors package baseline, so this package is closure-first for vLLM compressed-tensors quantization lanes.
- Uses the vLLM 0.20.1-compatible compressed-tensors 0.15.0.1 release instead of the older 0.14.0.1 helper version named by Blackcat's llmcompressor quantization notes.
- Treat llmcompressor as a separate package/dependency-closure decision because llmcompressor 0.10.0.1 pins compressed-tensors 0.14.0.1 and older torch/transformers bounds than the current local stack.

## Update Notes

- Check vLLM's requirements/common.txt and compressed-tensors release metadata together before updating; this package should stay compatible with the installed vLLM quantization import path.
- After publishing a rebuilt package, verify `import compressed_tensors` and a minimal config import through the installed local Python lane.
- Do not use this package as proof that llmcompressor is installable. Package llmcompressor only after its accelerate, auto-round, NVIDIA-management, torch, transformers, and compressed-tensors dependency story is reconciled.
- Keep the build dependency check skipped while upstream's sdist pins setuptools_scm==8.2.0. The Arch host carries a newer setuptools-scm that builds the pure-Python wheel cleanly.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
