# python-zstandard-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: ``
- Package version: `0.25.0`
- Recipe revision: `a188f9e (20260424, 10 path commits)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-zstandard, cachyos-extra-znver4/python-zstandard`
- Authoritative reference package: `extra/python-zstandard`
- Advisory reference packages: `cachyos-extra-znver4/python-zstandard`
- Applied source patch files/actions: `1`

## Recipe notes

Builds and installs numpy, sentencepiece, zstandard, asyncpg, duckdb from
source with Zen 5 optimization flags.

numpy: cmake pip wrapper breaks in build isolation; replaced with
symlink to system cmake.

meson-based packages (numpy, zstandard): -mllvm flags must be
rewritten as -Xclang -mllvm -Xclang pairs because meson's compiler
probing rejects -mllvm as "unused command line argument".
-famd-opt moved to LDFLAGS (link-time-only driver flag, no-op at
compile time -- triggers -Werror=unused in compile-only probes).

## Scaffold notes

- Treat this like the recipe's native wheel class so the same clang flag rewrite is available if the backend performs compiler probes.

## Intentional Divergences

- Mostly follows the Arch package shape while staying in the recipe's generic native-wheel compiler lane.
- Uses the optimized Python package as the interpreter baseline.

## Update Notes

- Check Arch first for backend or dependency changes, then keep Cachy only as a secondary packaging reference.
- If this package starts probing compiler features more aggressively, ensure the recipe's flag-rewrite logic still keeps the build deterministic.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
