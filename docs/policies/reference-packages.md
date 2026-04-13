# Reference Package Policy

This policy explains how each recipe-managed package chooses a baseline
PKGBUILD, how that choice is recorded, and how future updates should use it.

## Why This Exists

The package renderer is recipe-driven, but it is not recipe-only. Each package
also needs a clear Arch-facing maintenance story:

- which package recipe is the main baseline
- which nearby packages are only advisory
- where this repo deliberately diverges
- how a future maintainer should approach updates

If that information lives only in chat history, update work becomes brittle.

## Selection Rule

Choose the same or closest compatibility lane first. Only then rank sources
within that lane.

Compatibility lane means, as closely as available:

- same toolchain family
- same accelerator/runtime family
- same architecture specificity
- same major.minor version lane

Within that lane, prefer:

1. CachyOS
2. Arch
3. AUR

If no package exists in the exact lane, use the closest available package. Do
not treat that as "no baseline exists" unless there is truly no useful package
to start from.

Out-of-lane packages are still useful, but only as advisory references.

## Required Maintenance Metadata

Each recipe-managed package should expose the following maintenance fields in
its generated `packages/<name>/recipe.json` and `packages/<name>/README.md`:

- `authoritative_reference`
- `advisory_references`
- `divergence_notes`
- `update_notes`

Those fields come from `policies/recipe-packages.toml`. If they are omitted,
the renderer derives the authoritative reference from the first
`arch_reference` entry and the advisory references from the remainder. That
default is acceptable for straightforward packages, but explicit values are
preferred when:

- there is no real standalone baseline package
- the closest backend-specific package is binary-only
- the source lane deliberately differs from the baseline package
- the package is a meta package rather than a direct build output

## How To Use The Metadata

When updating or auditing a package:

1. Read the package's generated `recipe.json`.
2. Confirm the `authoritative_reference` still makes sense.
3. Check whether the `advisory_references` reveal a better current baseline.
4. Reconcile every `divergence_note` with the current upstream, baseline
   package, and recipe.
5. Treat `update_notes` as the package-specific checklist for the next change.

This metadata exists to make a fresh-context update story legible. An agent
should be able to answer, from files alone:

- what package to diff first
- what nearby packages are still worth scouting
- which divergences are deliberate
- which follow-up checks are mandatory after an update

## Practical Examples

- `python-gfx1151`
  - authoritative: `core/python`
  - advisory: `cachyos-znver4/python`
  - rationale: Python itself is not ROCm-versioned, so Arch system integration
    is the primary baseline and CachyOS is a secondary tuning reference.

- `python-pytorch-opt-rocm-gfx1151`
  - authoritative: `extra/python-pytorch-opt-rocm`
  - advisory: `extra/python-pytorch-rocm`,
    `cachyos-extra-znver4/python-pytorch-opt-rocm`
  - rationale: keep the Arch split-package shape, but use the ROCm fork and
    recipe patches for the source lane.

- `llama.cpp-hip-gfx1151`
  - authoritative: `aur/llama.cpp-hip`
  - advisory: `aur/llama.cpp`
  - rationale: the backend-specific AUR package is the closest maintained HIP
    lane; the generic package is still useful for shared conventions.

- `llama.cpp-vulkan-gfx1151`
  - authoritative: `aur/llama.cpp-vulkan-bin`
  - advisory: `aur/llama.cpp`
  - rationale: the closest Vulkan-specific reference is currently binary-only,
    so it is authoritative for package expectations but only advisory for
    source-build mechanics.

- `aocl-libm-gfx1151`
  - authoritative: `none`
  - advisory: `aur/aocl`
  - rationale: there is no standalone AOCL-LibM package in Arch-family repos,
    so the package is recipe-first and the broader AOCL bundle is advisory.

## Renderer Expectations

`tools/render_recipe_scaffolds.py` should fail loudly when a new package class
or patching mode cannot be expressed cleanly. Failure output should tell a
future maintainer what is missing:

- package selection rule
- new template support
- unsupported patch type
- missing recipe package entry

That is intentional. Silent fallback is worse than a clear failure here.
