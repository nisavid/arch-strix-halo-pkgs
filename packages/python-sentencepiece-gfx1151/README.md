# python-sentencepiece-gfx1151

## Maintenance Snapshot

- Recipe package key: `native_wheels`
- Scaffold template: `native-wheel-pypi`
- Recipe build method: `pip`
- Upstream repo: ``
- Derived pkgver seed: `0.2.1.r8.d20260317.gad42886`
- Recipe steps: `31`
- Recipe dependencies: `cpython, pytorch`
- Recorded reference packages: `cachyos/python-sentencepiece, aur/python-sentencepiece, aur/python-sentencepiece-git`
- Authoritative reference package: `cachyos/python-sentencepiece`
- Advisory reference packages: `aur/python-sentencepiece, aur/python-sentencepiece-git`
- Applied source patch files/actions: `1`
- Active source patch: `0001-bundle-sentencepiece-by-default.patch` (prefers bundled sentencepiece build by default, only uses system `pkg-config sentencepiece` when `SENTENCEPIECE_USE_SYSTEM=1` is explicitly set)

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

The repo-built package artifacts show the bundled-build patch is effective: the
current built `_sentencepiece` extension under `packages/.../pkg/` no longer
depends on `libsentencepiece.so.0` or `libsentencepiece_train.so.0`.

The concrete host Gemma 4 failure happened because the host still had the older
installed `python-sentencepiece-gfx1151 0.2.1.r8.d20260317.gad42886-1` package,
whose installed extension still resolved stale host `sentencepiece` shared
libraries.

## Scaffold notes

- The current CachyOS python-sentencepiece package is the closest maintained baseline, while the AUR python-sentencepiece and python-sentencepiece-git packages remain advisory references for patching and split-package expectations.
- The original recipe fixes a broken pip-installed cmake wrapper inside the venv. In Arch packaging that should translate to using the system cmake toolchain directly.

## Intentional Divergences

- Uses the closest maintained Cachy baseline but applies the recipe's system-cmake packaging translation instead of relying on a pip-installed cmake wrapper.
- Stays on a source-build path even though a git variant exists, because the release package is the primary maintenance lane.

## Update Notes

- Re-check against Cachy first, then consult the AUR source and git variants if the maintained package lags a needed upstream change.
- If the upstream build backend changes, keep the package metadata focused on the system cmake/toolchain story rather than reviving venv-local wrapper assumptions.
- After publishing a rebuilt package, verify the installed host extension with
  `readelf -d` or `ldd` so the live system is not still carrying the older
  pre-bundle artifact.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
