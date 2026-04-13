# TheRock Split Generator

## Purpose

`generators/therock_split.py` scaffolds the local Arch split-package ROCm
family from a staged TheRock install tree.

`tools/render_therock_pkgbase.py` is the normal operator entrypoint. It wraps
the generator, computes the recipe-derived `pkgver`, stamps attribution, and
renders the package base into `packages/therock-gfx1151/`.

The design goal is:

1. automate ownership assignment for known component classes
2. keep package metadata in a policy file rather than hardcoding it in the
   generator
3. fail with explicit machine-readable diagnostics for new or ambiguous
   components

The generator is intentionally strict. A loud structural failure is better than
silently assigning new TheRock content to the wrong package.

## Inputs

- `--root`: filesystem root containing the staged install tree, default `/`
- `--policy`: policy file, default `policies/therock-packages.toml`
- `--output`: generated output directory
- `--pkgver-override`: rendered package version override
- recipe attribution flags used by `render_therock_pkgbase.py`

The policy currently assumes the actual TheRock payload lives under
`opt/rocm/`.

## Failure codes

The generator exits non-zero if it cannot classify the tree cleanly.

Structured diagnostics are emitted in this shape:

- `UNMAPPED_COMPONENT: <path>`
- `AMBIGUOUS_OWNERSHIP: <path> -> <pkg1>,<pkg2>`
- `NEW_THEROCK_PACKAGE_CLASS: <class> from <path>`
- `MISSING_PACKAGE_METADATA: <pkg>`

Each failure also includes a short hint explaining whether the fix belongs in:

- path ownership overrides
- component alias mapping
- package metadata definitions
- meta package dependency definitions

## Typical update workflow

1. Build or stage a new TheRock tree.
2. Run `python tools/render_therock_pkgbase.py --recipe-root /path/to/ai-notes`.
3. If it fails:
   - add aliases for known new component directories or file prefixes
   - add explicit path ownership overrides for outliers
   - add package metadata if a package name is new
4. Re-run until ownership is total and unambiguous.
5. Build the rendered package base under `packages/therock-gfx1151/`.
6. Publish refreshed artifacts through the local repo workflow in
   `docs/usage/local-repo.md`.
