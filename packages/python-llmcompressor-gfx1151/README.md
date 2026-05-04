# python-llmcompressor-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/vllm-project/llm-compressor`
- Package version: `0.10.0.1`
- Recipe revision: `a1d7a68 (20260427, 16 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `none`
- Authoritative reference package: `none`
- Advisory reference packages: `none`
- Applied source patch files/actions: `5`

## Recipe notes

This package supplies llmcompressor for the Blackcat Qwen3-VL
quantization/tooling follow-up lane. Blackcat's helper notes name
llmcompressor 0.10.0.1 with release metadata that pins older torch,
transformers, and compressed-tensors bounds than the current local stack.

The package builds with llmcompressor's dev dependency lane so torch and
compressed-tensors can follow the installed vLLM 0.20.1 stack, and carries a
small metadata patch to remove the remaining Transformers upper bound. It also
carries compatibility patches for the current Transformers and
compressed-tensors APIs. The build sets `SETUPTOOLS_SCM_PRETEND_VERSION=0.10.0.1`
so the PyPI sdist build keeps the adopted release version.

llmcompressor declares nvidia-ml-py as a runtime dependency even though pynvml
is imported lazily only for NVIDIA metric logging. The local package patches
that dependency out of the built wheel metadata so AMD installs do not need a
repo-owned NVML shim or NVIDIA driver utilities.


## Scaffold notes

- Part of the Blackcat Qwen3-VL quantization/tooling closure.
- Keep dependencies pointed at the local accelerate, AutoRound, compressed-tensors, torch, transformers, Pillow, and PyYAML packages.
- Use --skip-dependency-check to avoid the stale exact setuptools_scm build pin and local-package-name metadata mismatch.
- Keep BUILD_TYPE=dev plus the Transformers compatibility patches unless upstream release metadata and imports accept the installed torch, transformers, and compressed-tensors stack directly.

## Intentional Divergences

- There is no current Arch-family llmcompressor package baseline, so this package is closure-first for Blackcat's Qwen3-VL quantization/tooling notes.
- Builds with llmcompressor's dev dependency lane and a package-local metadata patch so the installed package accepts the local torch 2.11, transformers 5.7, and compressed-tensors 0.15 stack.
- Carries a package-local Transformers 5.7 compatibility patch for the moved `TORCH_INIT_FUNCTIONS` import.
- Carries a package-local compressed-tensors 0.15 compatibility patch for the public `match_name` API replacing the former private `_match_name` import.
- Carries a package-local compressed-tensors 0.15 compatibility patch for the moved quantization compression-format helper.
- Carries a package-local metadata patch so NVIDIA metric logging remains optional on the AMD reference host instead of requiring nvidia-ml-py.

## Update Notes

- Check torch, transformers, compressed-tensors, accelerate, and auto-round bounds together before updating.
- After publishing a rebuilt package, verify `import llmcompressor` and the AutoRound modifier import through the installed local Python lane.
- Use `SETUPTOOLS_SCM_PRETEND_VERSION` when building from the PyPI sdist so the package version stays at the adopted release instead of a guessed dev version.
- Keep the build dependency check skipped while upstream's sdist pins setuptools_scm==8.2.0 and local runtime dependencies satisfy metadata under gfx1151 package names.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
