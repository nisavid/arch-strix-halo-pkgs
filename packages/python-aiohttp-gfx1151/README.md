# python-aiohttp-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://aiohttp.readthedocs.io`
- Package version: `3.13.5`
- Recipe revision: `a1d7a68 (20260427, 16 path commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-aiohttp`
- Authoritative reference package: `extra/python-aiohttp`
- Advisory reference packages: `none`
- Applied source patch files/actions: `1`

## Recipe notes

This package is the aiohttp output from the shared `native_wheels` recipe
phase. That phase also builds numpy, sentencepiece, zstandard, asyncpg,
duckdb, PyYAML, psutil, Pillow, uvloop, httptools, msgspec, multidict, yarl,
and frozenlist from source with Zen 5 optimization flags, but those outputs
are tracked as separate packages or follow-up package lanes rather than as
dependencies of `python-aiohttp-gfx1151`.

aiohttp supplies async HTTP client/server helpers used by service paths. The
local package follows Arch's system-dependency shape with
AIOHTTP_USE_SYSTEM_DEPS=1 while moving its native extensions onto the local
amdclang native-wheel lane.


## Scaffold notes

- Part of the comprehensive Blackcat service/runtime wheel stack and consumed by the local vLLM package.
- Keep dependencies pointed at the local frozenlist, multidict, and yarl packages so the aiohttp closure stays on the repo-owned optimized stack.

## Intentional Divergences

- Follows Arch's python-aiohttp system-dependency package shape while rebuilding native extensions through the Blackcat native-wheel compiler lane.
- Keeps async HTTP client/server helpers for vLLM/FastAPI service paths on the repo-owned optimized wheel stack.

## Update Notes

- Check Arch first for llhttp, Cython, and dependency metadata before updating.
- Keep AIOHTTP_USE_SYSTEM_DEPS=1 in the build environment unless upstream changes how system llhttp is selected.
- After publishing a rebuilt package, verify `import aiohttp` and a minimal ClientSession construction path through the installed local Python lane.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
