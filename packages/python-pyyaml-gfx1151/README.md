# python-pyyaml-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: ``
- Package version: `6.0.3`
- Recipe revision: `a1d7a68 (20260427, 16 path commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-yaml, cachyos-extra-znver4/python-yaml`
- Authoritative reference package: `extra/python-yaml`
- Advisory reference packages: `cachyos-extra-znver4/python-yaml`
- Applied source patch files/actions: `1`

## Recipe notes

This package is the PyYAML output from the shared `native_wheels` recipe
phase. That phase also builds numpy, sentencepiece, zstandard, asyncpg,
duckdb, psutil, Pillow, uvloop, httptools, msgspec, aiohttp, multidict,
yarl, and frozenlist from source with Zen 5 optimization flags, but those
outputs are tracked as separate packages or follow-up package lanes rather
than as dependencies of `python-pyyaml-gfx1151`.

PyYAML keeps Arch's libYAML-backed package shape while moving the C extension
onto the same amdclang native-wheel lane as the other Blackcat C/C++ wheel
outputs.


## Scaffold notes

- Part of the core Blackcat model/config stack and used by PyTorch, AOTriton, and Transformers metadata/config paths.
- The package name is python-pyyaml-gfx1151, but it provides python-yaml to satisfy Arch-style dependencies.

## Intentional Divergences

- Follows Arch's python-yaml package shape while rebuilding the native extension through the Blackcat native-wheel compiler lane.
- Provides both python-yaml and python-pyyaml so existing Arch-style dependencies and PyPI-style package references resolve to the local package.

## Update Notes

- Check Arch python-yaml first for Cython, libyaml, and build-backend changes before updating.
- After publishing a rebuilt package, verify `import yaml` and confirm the libYAML-backed loader is available through the installed local Python lane.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
