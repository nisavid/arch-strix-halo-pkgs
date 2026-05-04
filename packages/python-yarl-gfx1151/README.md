# python-yarl-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/aio-libs/yarl/`
- Package version: `1.23.0`
- Recipe revision: `a1d7a68 (20260427, 16 path commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-yarl, cachyos-extra-znver4/python-yarl`
- Authoritative reference package: `extra/python-yarl`
- Advisory reference packages: `cachyos-extra-znver4/python-yarl`
- Applied source patch files/actions: `1`

## Recipe notes

This package is the yarl output from the shared `native_wheels` recipe phase.
That phase also builds numpy, sentencepiece, zstandard, asyncpg, duckdb,
PyYAML, psutil, Pillow, uvloop, httptools, msgspec, aiohttp, multidict, and
frozenlist from source with Zen 5 optimization flags, but those outputs are
tracked as separate packages or follow-up package lanes rather than as
dependencies of `python-yarl-gfx1151`.

yarl is part of aiohttp's native URL/dependency closure and belongs in the
same optimized service/runtime stack.


## Scaffold notes

- Part of the comprehensive Blackcat aiohttp service dependency closure and consumed by the local aiohttp package.
- Use the shared native-wheel renderer so amdclang, path remapping, and Zen 5 flags stay aligned with the other native wheel packages.

## Intentional Divergences

- Follows Arch's python-yarl package shape while rebuilding the native extension through the Blackcat native-wheel compiler lane.
- Keeps the aiohttp service dependency closure on the repo-owned optimized wheel stack.

## Update Notes

- Check Arch first for release and build-backend metadata before updating.
- After publishing a rebuilt package, verify `import yarl` and a minimal URL construction probe through the installed local Python lane.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
