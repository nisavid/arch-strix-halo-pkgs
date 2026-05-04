# python-psutil-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/giampaolo/psutil`
- Package version: `7.2.2`
- Recipe revision: `a1d7a68 (20260427, 16 patch commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-psutil`
- Authoritative reference package: `extra/python-psutil`
- Advisory reference packages: `none`
- Applied source patch files/actions: `0`

## Recipe notes

This package is the psutil output from the shared `native_wheels` recipe
phase. That phase also builds numpy, sentencepiece, zstandard, asyncpg,
duckdb, PyYAML, Pillow, uvloop, httptools, msgspec, aiohttp, multidict,
yarl, and frozenlist from source with Zen 5 optimization flags, but those
outputs are tracked as separate packages or follow-up package lanes rather
than as dependencies of `python-psutil-gfx1151`.

psutil supplies native process and system telemetry used by schedulers,
monitors, and vLLM service paths, so it belongs in the local optimized core
stack rather than relying on the generic distro wheel.


## Scaffold notes

- Part of the core Blackcat model/config stack and consumed by the local vLLM package.
- Use the shared native-wheel renderer so amdclang, path remapping, and Zen 5 flags stay aligned with the other native wheel packages.

## Intentional Divergences

- Follows Arch's python-psutil package shape while rebuilding the native extension through the Blackcat native-wheel compiler lane.
- Keeps vLLM scheduler and service telemetry on the repo-owned Python/native-extension stack.

## Update Notes

- Check Arch first for release and dependency metadata before updating.
- After publishing a rebuilt package, verify `import psutil` and a minimal process or virtual-memory probe through the installed local Python lane.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
