# python-zstandard-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: `https://github.com/indygreg/python-zstandard`
- Package version: `0.25.0`
- Recipe revision: `a1d7a68 (20260427, 16 commits touching recipe path)`
- Recipe steps: `32`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-zstandard, cachyos-extra-znver4/python-zstandard`
- Authoritative reference package: `extra/python-zstandard`
- Advisory reference packages: `cachyos-extra-znver4/python-zstandard`
- Applied source patch files/actions: `0`

## Recipe notes

This package is the zstandard output from the shared `native_wheels` recipe
phase. That phase also builds numpy, sentencepiece, asyncpg, duckdb, PyYAML,
psutil, Pillow, uvloop, httptools, msgspec, aiohttp, multidict, yarl, and
frozenlist from source with Zen 5 optimization flags, but those outputs are
tracked as separate packages or follow-up package lanes rather than as
dependencies of `python-zstandard-gfx1151`.

zstandard participates in the same meson/native compiler flag lane as NumPy:
-mllvm flags must be rewritten as -Xclang -mllvm -Xclang pairs because
meson's compiler probing rejects -mllvm as "unused command line argument".
-famd-opt moves to LDFLAGS because it is a link-time-only driver flag and
triggers -Werror=unused in compile-only probes.


## Scaffold notes

- Treat this like the recipe's native wheel class so the same clang flag rewrite is available if the backend performs compiler probes.

## Intentional Divergences

- Mostly follows the Arch package shape while staying in the recipe's generic native-wheel compiler lane.
- Uses the optimized Python package as the interpreter baseline.

## Update Notes

- Check Arch first for backend or dependency changes, then keep Cachy only as a secondary packaging reference.
- If this package starts probing compiler features more aggressively, ensure the recipe's flag-rewrite logic still keeps the build deterministic.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
