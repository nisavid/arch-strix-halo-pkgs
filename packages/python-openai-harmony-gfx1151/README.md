# python-openai-harmony-gfx1151

## Maintenance Snapshot

- Recipe package key: `rust_wheels`
- Scaffold template: `rust-wheel-pypi`
- Recipe build method: `cargo`
- Upstream repo: `https://github.com/openai/harmony`
- Package version: `0.0.8`
- Recipe revision: `3f15f9f (20260508, 17 commits touching recipe path)`
- Recipe steps: `31`
- Recipe dependencies: `cpython`
- Recorded reference packages: `aur/python-openai-harmony, aur/python-openai-harmony-git`
- Authoritative reference package: `aur/python-openai-harmony`
- Advisory reference packages: `aur/python-openai-harmony-git`
- Applied source patch files/actions: `0`

## Recipe notes

Builds openai-harmony from the published PyPI sdist using upstream's maturin
PEP 517 backend and thin PyO3 bindings over the Rust core.

Keep explicit znver5 CPU targeting and opt-level=3 in RUSTFLAGS because the
repo documents rustc native-detection drift on this host class. Do not force
extra -C lto flags through RUSTFLAGS unless the current maturin/cargo lane is
verified compatible.

No maintainable package-level PGO flow is exposed upstream today, so this
package currently stops at the applicable CPU-tuning and release-profile
settings.


## Scaffold notes

- The AUR baseline currently omits upstream's python-pydantic runtime dependency, so this scaffold carries the complete closure from the published project metadata instead of copying the PKGBUILD blindly.
- The package uses the PyPI sdist rather than a git+tag source fetch because upstream publishes matching source archives and the pyproject.toml build metadata is authoritative there.
- Keep the Rust linker pinned to the AMD toolchain lane and the CPU target pinned to znver5; if future rustc native detection becomes trustworthy here, that can be re-evaluated package by package.

## Intentional Divergences

- Follows the repo's Rust-wheel compiler lane with explicit AMD toolchain selection and znver5 CPU targeting instead of the generic distro compiler defaults.
- Uses the published PyPI sdist and upstream maturin build metadata rather than the AUR package's git+tag source fetch, while still treating the AUR package as the authoritative Arch-family baseline.

## Update Notes

- Check the current AUR python-openai-harmony package first, then confirm upstream pyproject.toml build-backend and dependency metadata before carrying any build changes forward.
- Keep python-pydantic as a hard runtime dependency unless upstream removes it from the published project metadata.
- Treat extra Rust LTO or PGO tuning as opt-in only after verifying the current maturin/cargo lane exposes a maintainable configuration; today the applicable default is explicit znver5 plus opt-level=3.
- On 2026-09-25, bump pkgrel to 2 for the generation-C W2A closure (#110, #111), to be built in the rootless C build root against TheRock 7.14.1 and python-gfx1151 3.14.7 in the vLLM lease job. The source is unchanged; the rebuild keeps the package out of the previous generation's repo. vLLM imports it while `vllm serve` parses its arguments, so the W2A root needs a generation-C build. The rust-wheel template keeps `CARGO_HOME` under `$srcdir/.cargo`, which overrides the build helper's shared cargo cache, and sets `RUSTUP_AUTO_INSTALL=0`. The cargo fetch runs inside build(), so the build needs `enter --net`.

## Maintainer Starting Points

- If an authoritative reference exists, diff the package against it first; when none is recorded, start from the current policy and document the source of each change.
- Use advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
