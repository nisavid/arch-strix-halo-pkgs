# python-nvidia-ml-py-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://forums.developer.nvidia.com`
- Package version: `13.590.48`
- Recipe revision: `a1d7a68 (20260427, 16 patch commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-nvidia-ml-py`
- Authoritative reference package: `none`
- Advisory reference packages: `extra/python-nvidia-ml-py`
- Applied source patch files/actions: `1`

## Recipe notes

This package supplies the `pynvml` module named by llmcompressor metadata
without depending on NVIDIA driver utilities. llmcompressor's NVIDIA metric
path imports pynvml lazily and returns an empty usage result when the module or
NVML library is unavailable, while AMD metric logging uses amdsmi separately.

Use this package only as metadata and import closure for llmcompressor on the
AMD reference host. A failing NVML initialization on AMD is expected and is not
evidence that the package is broken.


## Scaffold notes

- Part of the Blackcat Qwen3-VL quantization/tooling closure and consumed by llmcompressor metadata.
- Do not add an nvidia-utils dependency; this package exists specifically to keep the AMD host free of NVIDIA driver packages.

## Intentional Divergences

- Arch's python-nvidia-ml-py package depends on nvidia-utils, which is not appropriate for the AMD reference host.
- llmcompressor imports pynvml lazily only for NVIDIA metric logging, but its package metadata declares nvidia-ml-py as a runtime dependency, so this package satisfies metadata without installing the NVIDIA driver stack.

## Update Notes

- Keep this package pinned to the llmcompressor dependency window unless llmcompressor drops the hard metadata dependency or Arch separates the Python bindings from nvidia-utils.
- After publishing a rebuilt package, verify `import pynvml` through the installed local Python lane; do not treat NVML initialization failure on AMD as a package failure.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
