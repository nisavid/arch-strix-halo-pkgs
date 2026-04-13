# aocl-libm-gfx1151

## Maintenance Snapshot

- Recipe package key: `aocl_libm`
- Scaffold template: `scons-aocl-libm`
- Recipe build method: `scons`
- Upstream repo: `https://github.com/amd/aocl-libm-ose.git`
- Derived pkgver seed: `5.2.1.r8.d20260317.gad42886`
- Recipe steps: `6`
- Recipe dependencies: `therock, aocl_utils`
- Recorded reference packages: `aur/aocl`
- Authoritative reference package: `none`
- Advisory reference packages: `aur/aocl`
- Applied source patch files/actions: `4`

## Recipe notes

Zen 5 optimized transcendentals (exp, log, sin, cos, pow) with
AVX-512 codepaths for native 512-bit execution on Strix Halo.

NOT linked into CPython directly: AOCL-LibM has slightly different
ULP rounding than glibc libm (cbrt(-0.0) -> +0.0, nextafter broken
for subnormals), which causes CPython's PGO test_math to fail.
Available at runtime via LD_LIBRARY_PATH for NumPy and PyTorch.

## Scaffold notes

- There is no standalone AOCL-LibM package in Arch, CachyOS, or AUR; the closest packaging lane is the broader AUR aocl bundle, which is only advisory for install-layout cleanup patterns.
- The recipe carries three upstream-compatibility patch steps plus a post-install RPATH fix; those are rendered into prepare() and package().
- Keep AOCL-LibM out of the CPython link line. It is intended for downstream numerical libraries, not Python's own PGO run.
- Build testing showed libalm.so does not advertise a versioned SONAME, so the scaffold does not export it in provides().

## Intentional Divergences

- There is no standalone Arch-family AOCL-LibM package, so this package is recipe-first and uses the broader aur/aocl bundle only for install-layout and metadata expectations.
- The package keeps AOCL-LibM out of CPython's own link line; it is intended as a downstream math library, not part of Python's PGO training path.

## Update Notes

- When updating, audit upstream AOCL-LibM licensing and bundled notices directly from source rather than assuming the advisory aur/aocl metadata is sufficient.
- If AOCL-Utils packaging changes, re-check the runtime dependency and any RPATH or SONAME assumptions here.

## Maintainer Starting Points

- Diff the package against its recorded authoritative reference first.
- Use the advisory references to scout neighboring packaging conventions without silently changing the baseline story.
- Keep reusable source changes in sibling patch files rather than leaving them as ad hoc PKGBUILD shell edits.
- Re-run `tools/render_recipe_scaffolds.py` after policy or recipe-manifest changes so the package-local docs stay in sync.
