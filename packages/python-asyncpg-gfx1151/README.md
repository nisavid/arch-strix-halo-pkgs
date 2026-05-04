# python-asyncpg-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/MagicStack/asyncpg`
- Package version: `0.31.0`
- Recipe revision: `a1d7a68 (20260427, 16 patch commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-asyncpg, cachyos-extra-znver4/python-asyncpg`
- Authoritative reference package: `extra/python-asyncpg`
- Advisory reference packages: `cachyos-extra-znver4/python-asyncpg`
- Applied source patch files/actions: `1`

## Recipe notes

This package is the asyncpg output from the shared `native_wheels` recipe
phase. That phase also builds numpy, sentencepiece, zstandard, duckdb, PyYAML,
psutil, Pillow, uvloop, httptools, msgspec, aiohttp, multidict, yarl, and
frozenlist from source with Zen 5 optimization flags, but those outputs are
tracked as separate packages or follow-up package lanes rather than as
dependencies of `python-asyncpg-gfx1151`.

asyncpg uses the recipe's generic native-wheel compiler lane even though its
build backend differs from meson-based packages in the same phase.


## Scaffold notes

- This package is grouped under the recipe's native wheel build step even though its build backend differs from meson-based numpy.

## Intentional Divergences

- Uses the recipe's generic native-wheel compiler lane even though asyncpg's backend differs from meson-based packages in the same group.
- Uses the optimized Python package as the interpreter baseline.

## Update Notes

- Check Arch first for Cython/backend drift and ABI expectations, then use Cachy as a secondary reference.
- If asyncpg starts requiring PostgreSQL client headers or additional runtime linkage, record that change explicitly in package metadata.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
