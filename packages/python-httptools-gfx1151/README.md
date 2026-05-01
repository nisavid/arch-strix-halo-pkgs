# python-httptools-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: ``
- Package version: `0.7.1`
- Recipe revision: `a1d7a68 (20260427, 16 path commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-httptools, cachyos-extra-znver4/python-httptools`
- Authoritative reference package: `extra/python-httptools`
- Advisory reference packages: `cachyos-extra-znver4/python-httptools`
- Applied source patch files/actions: `2`

## Recipe notes

This package is the httptools output from the shared `native_wheels` recipe
phase. That phase also builds numpy, sentencepiece, zstandard, asyncpg,
duckdb, PyYAML, psutil, Pillow, uvloop, msgspec, aiohttp, multidict, yarl,
and frozenlist from source with Zen 5 optimization flags, but those outputs
are tracked as separate packages or follow-up package lanes rather than as
dependencies of `python-httptools-gfx1151`.

httptools supplies the native HTTP parser used by uvicorn standard service
paths. The local package follows Arch's system-llhttp shape while moving the
native extension onto the local amdclang native-wheel lane.


## Scaffold notes

- Part of the comprehensive Blackcat service/runtime wheel stack and consumed by the local vLLM package.
- Keep the source patch that switches httptools' build_ext default to system llhttp so the local package does not vendor a private llhttp copy.

## Intentional Divergences

- Follows Arch's python-httptools system-llhttp package shape while rebuilding the native extension through the Blackcat native-wheel compiler lane.
- Keeps uvicorn/vLLM HTTP parsing on the repo-owned optimized wheel stack.

## Update Notes

- Check Arch first for llhttp and Cython build metadata before updating.
- Keep the package-local system-llhttp patch unless upstream changes the build backend to expose a stable PEP 517 config setting for the same choice.
- Keep `skip_dependency_check = true` while the PyPI sdist pins an exact setuptools build requirement; Arch builds httptools from source without that equality gate, and this package uses the repo's system setuptools in the same no-isolation lane.
- After publishing a rebuilt package, verify `import httptools` through the installed local Python lane.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
