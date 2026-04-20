# python-asyncpg-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: ``
- Package version: `0.31.0`
- Recipe revision: `ad42886 (20260317, 8 path commits)`
- Recipe steps: `31`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-asyncpg, cachyos-extra-znver4/python-asyncpg`
- Authoritative reference package: `extra/python-asyncpg`
- Advisory reference packages: `cachyos-extra-znver4/python-asyncpg`
- Applied source patch files/actions: `1`

## Recipe notes

Builds and installs numpy, sentencepiece, zstandard, asyncpg from
source with Zen 5 optimization flags.

numpy: cmake pip wrapper breaks in build isolation; replaced with
symlink to system cmake.

meson-based packages (numpy, zstandard): -mllvm flags must be
rewritten as -Xclang -mllvm -Xclang pairs because meson's compiler
probing rejects -mllvm as "unused command line argument".
-famd-opt moved to LDFLAGS (link-time-only driver flag, no-op at
compile time -- triggers -Werror=unused in compile-only probes).

## Scaffold notes

- This package is grouped under the recipe's native wheel build step even though its build backend differs from meson-based numpy.

## Intentional Divergences

- Uses the recipe's generic native-wheel compiler lane even though asyncpg's backend differs from meson-based packages in the same group.
- Uses the optimized Python package as the interpreter baseline.

## Update Notes

- Check Arch first for Cython/backend drift and ABI expectations, then use Cachy as a secondary reference.
- If asyncpg starts requiring PostgreSQL client headers or additional runtime linkage, record that change explicitly in package metadata.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
