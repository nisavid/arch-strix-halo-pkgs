# python-frozenlist-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/aio-libs/frozenlist`
- Package version: `1.8.0`
- Recipe revision: `a1d7a68 (20260427, 16 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-frozenlist, cachyos-extra-znver4/python-frozenlist`
- Authoritative reference package: `extra/python-frozenlist`
- Advisory reference packages: `cachyos-extra-znver4/python-frozenlist`
- Applied source patch files/actions: `0`

## Recipe notes

frozenlist is part of aiohttp's native dependency closure. This package
keeps that direct C-extension surface on the local amdclang native-wheel lane
while following Arch's python-frozenlist package shape.


## Scaffold notes

- Part of the comprehensive Blackcat aiohttp service dependency closure.
- Use the shared native-wheel renderer so amdclang, path remapping, and Zen 5 flags stay aligned with the other native wheel packages.

## Intentional Divergences

- Follows Arch's python-frozenlist package shape while rebuilding the native extension through the Blackcat native-wheel compiler lane.
- Keeps the aiohttp service dependency closure on the repo-owned optimized wheel stack.

## Update Notes

- Check Arch first for release and build-backend metadata before updating.
- After publishing a rebuilt package, verify `import frozenlist` and a minimal FrozenList construction probe through the installed local Python lane.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
