# python-uvloop-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/MagicStack/uvloop`
- Package version: `0.22.1`
- Recipe revision: `a1d7a68 (20260427, 16 path commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-uvloop, cachyos-extra-znver4/python-uvloop`
- Authoritative reference package: `extra/python-uvloop`
- Advisory reference packages: `cachyos-extra-znver4/python-uvloop`
- Applied source patch files/actions: `2`

## Recipe notes

This package is the uvloop output from the shared `native_wheels` recipe
phase. That phase also builds numpy, sentencepiece, zstandard, asyncpg,
duckdb, PyYAML, psutil, Pillow, httptools, msgspec, aiohttp, multidict,
yarl, and frozenlist from source with Zen 5 optimization flags, but those
outputs are tracked as separate packages or follow-up package lanes rather
than as dependencies of `python-uvloop-gfx1151`.

uvloop supplies the libuv-backed asyncio event loop used by vLLM/FastAPI
service paths. The local package follows Arch's system-libuv shape while
moving the native extension onto the local amdclang native-wheel lane.


## Scaffold notes

- Part of the comprehensive Blackcat service/runtime wheel stack and consumed by the local vLLM package.
- Keep the source patch that switches uvloop's build_ext default to system libuv so the local package does not vendor a private libuv copy.

## Intentional Divergences

- Follows Arch's python-uvloop system-libuv package shape while rebuilding the native extension through the Blackcat native-wheel compiler lane.
- Keeps vLLM and FastAPI service event loops on the repo-owned optimized wheel stack.

## Update Notes

- Check Arch first for libuv and Cython build metadata before updating.
- Keep the package-local system-libuv patch unless upstream changes the build backend to expose a stable PEP 517 config setting for the same choice.
- After publishing a rebuilt package, verify `import uvloop` and a minimal `uvloop.new_event_loop()` probe through the installed local Python lane.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
