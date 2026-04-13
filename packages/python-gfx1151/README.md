# python-gfx1151

## Maintenance Snapshot

- Recipe package key: `cpython`
- Scaffold template: `autoconf-python`
- Recipe build method: `autoconf`
- Upstream repo: `https://github.com/python/cpython.git`
- Derived pkgver seed: `3.14.4.r8.d20260317.gad42886`
- Recipe steps: `7`
- Recipe dependencies: `therock`
- Recorded reference packages: `core/python, cachyos-znver4/python`
- Authoritative reference package: `core/python`
- Advisory reference packages: `cachyos-znver4/python`
- Applied source patch files/actions: `0`

## Recipe notes

Python 3.13 built with PGO + LTO + amdclang for Zen 5.

PGO (Profile-Guided Optimization): runs the test suite as training
data, then recompiles with branch prediction hints. LTO (thin):
whole-program optimization across translation units.

CRITICAL: Must unset ALL vllm-env.sh flags before configure.
vllm-env.sh sets LDFLAGS=-lalm which autoconf merges with configure
LDFLAGS, causing AOCL-LibM to be linked, which breaks PGO training
(test_math fails on signed zero and subnormal number handling).

vllm-env.sh is re-sourced after build to restore flags.

## Scaffold notes

- This scaffold is intentionally rebased onto current Arch/Cachy Python 3.14.x instead of the recipe's older CPython 3.13.12 pin.
- The scaffold preserves the recipe's rule that all vllm-env.sh compiler flags must be unset before configure so AOCL-LibM does not contaminate the PGO training run.
- Before production cutover, verify feature parity with the current Arch python package, especially tkinter, sqlite extension loading, PEP 668, and debug-path sanitization.
- The scaffold intentionally disables ensurepip so pip stays split into separate packages, matching Arch system integration more closely.
- The scaffold uses the official CPython release tarball rather than a git mirror because the package is pinned to a tagged release and full VCS fetches are unnecessarily expensive here.
- Treat the system-Python replacement as gated on a successful Python-3.14 vLLM smoke test against the coherent TheRock ROCm stack.

## Intentional Divergences

- Uses the Arch system-Python package shape as the integration baseline while layering in the recipe's amdclang plus PGO/LTO approach.
- Intentionally keeps pip/setuptools split out of the base interpreter package and preserves Arch's externally managed environment behavior.

## Update Notes

- Always diff against the current Arch python PKGBUILD first, then inspect CachyOS for any CPU-tuning or toolchain deltas worth carrying.
- Treat system-Python replacement as gated on a fresh torch/vllm smoke run after any major Python, ROCm, or recipe change.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
- Reconfirm the chosen upstream source artifact and build lane before treating the scaffold as release-ready.
