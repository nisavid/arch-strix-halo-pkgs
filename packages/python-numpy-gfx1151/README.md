# python-numpy-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: ``
- Package version: `2.4.4`
- Recipe revision: `b453c33 (20260422, 9 path commits)`
- Recipe steps: `31`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-numpy, cachyos-extra-znver4/python-numpy`
- Authoritative reference package: `extra/python-numpy`
- Advisory reference packages: `cachyos-extra-znver4/python-numpy`
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

- The recipe's key fix here is the meson/clang flag rewrite: convert driver-level -mllvm flags to -Xclang pairs and move -famd-opt to LDFLAGS.
- Pins Meson BLAS and LAPACK to OpenBLAS so upstream NumPy does not auto-detect and link Intel oneMKL on mixed-provider hosts.

## Intentional Divergences

- Keeps the Arch package shape but carries the recipe's clang/meson flag rewrite so AMD-specific driver flags survive meson compiler probing.
- Uses the optimized Python package as the interpreter baseline rather than the distro python package.
- Pins NumPy BLAS/LAPACK to OpenBLAS explicitly to avoid oneMKL provider auto-selection on mixed-provider hosts.

## Update Notes

- Re-check BLAS/LAPACK provider handling and any Arch downstream patches whenever numpy or Python major/minor changes.
- Validate that OpenBLAS remains the active Meson provider after toolchain or Intel oneMKL updates, and keep the explicit provider pins if contamination returns.
- If future recipe changes add real source patches, keep them as patch files instead of further growing shell flag transforms.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
