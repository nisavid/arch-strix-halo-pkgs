# python-duckdb-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: ``
- Package version: `1.5.2`
- Recipe revision: `b453c33 (20260422, 9 path commits)`
- Recipe steps: `31`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `extra/python-duckdb, cachyos-extra-znver4/python-duckdb`
- Authoritative reference package: `extra/python-duckdb`
- Advisory reference packages: `cachyos-extra-znver4/python-duckdb`
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

- Embedded OLAP engine for local analytics and parquet scans; Blackcat added DuckDB to the native C/C++ wheel set.
- The package follows Arch's current `python-duckdb` metadata while building from the PyPI sdist with the same amdclang flag lane as the other recipe native wheels.
- DuckDB's source build uses scikit-build-core, CMake, Ninja, and pybind11; keep those as explicit makedepends rather than relying on isolated pip build dependency resolution.
- The build skips the Python frontend dependency check because DuckDB requests PyPI metadata names that do not match Arch's system package distribution metadata, even though the backend finds the system tools.

## Intentional Divergences

- Uses the Arch package shape while joining the Blackcat native-wheel recipe lane for Zen 5 source builds.
- Uses the optimized Python package as the interpreter baseline and keeps optional dataframe, Arrow, and filesystem integrations as optdepends.

## Update Notes

- Check Arch first for scikit-build-core, pybind11, bundled-extension, and optional dependency drift; use CachyOS only as the tuned-package neighbor.
- Keep `skip_dependency_check = true` while DuckDB's build-system metadata asks for PyPI distributions such as `pybind11[global]` and `cmake`; Arch supplies those build inputs as `pybind11` and `cmake`, so the no-isolation frontend dependency check is stricter than the actual build backend.
- Rebuild this package when DuckDB's bundled extension set or scikit-build-core metadata changes because those choices affect the Python extension ABI and packaged optional integrations.
- After publishing a rebuilt package, verify `import duckdb` and a tiny in-memory query through the installed local Python lane before using it in analytics/parquet workflows.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
