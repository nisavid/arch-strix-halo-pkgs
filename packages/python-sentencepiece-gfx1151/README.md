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

- The current CachyOS python-sentencepiece package is the closest maintained baseline, while the AUR python-sentencepiece and python-sentencepiece-git packages remain advisory references for patching and split-package expectations.
- The original recipe fixes a broken pip-installed cmake wrapper inside the venv. In Arch packaging that should translate to using the system cmake toolchain directly.

## Intentional Divergences

- Uses the closest maintained Cachy baseline but applies the recipe's system-cmake packaging translation instead of relying on a pip-installed cmake wrapper.
- Stays on a source-build path even though a git variant exists, because the release package is the primary maintenance lane.

## Update Notes

- Re-check against Cachy first, then consult the AUR source and git variants if the maintained package lags a needed upstream change.
- If the upstream build backend changes, keep the package metadata focused on the system cmake/toolchain story rather than reviving venv-local wrapper assumptions.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
