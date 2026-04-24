# Package Directory Guide

`packages/` contains both recipe-managed package roots and the generated
TheRock split-package base. Each directory is a package maintainer's starting
point, but the files you read first depend on the package type.

## How To Read A Package Directory

For a recipe-managed package named `<name>`, start with these files:

- `packages/<name>/README.md` for the human update summary
- `packages/<name>/recipe.json` for rendered maintenance metadata
- `packages/<name>/PKGBUILD` for the actual Arch package logic
- sibling `*.patch` files for durable source changes carried by the package

The package README explains the role, upstream source, reference package,
intentional divergences, update notes, and maintainer starting points. The
`recipe.json` keeps the same policy available to scripts.

For `packages/therock-gfx1151`, start with the PKGBUILD, generated manifest,
file lists, and the TheRock generator docs under `docs/architecture/` and
`docs/maintainers/`.

## Where The Package Set Comes From

Most recipe-managed package directories are rendered from:

- `tools/render_recipe_scaffolds.py`
- `policies/recipe-packages.toml`
- `upstream/ai-notes/strix-halo` recipe input

Rerun the recipe renderer whenever recipe notes, patch actions, package
baselines, or step assignments change so package-local READMEs and `recipe.json`
stay in sync with policy. The TheRock split-package base is rendered through
the separate generator path documented in `docs/architecture/therock-generator.md`.

## Package Roles

The current package set spans a few roles:

- **ROCm and host foundation:** TheRock split packages, AOCL utilities,
  AOCL-LibM, and the local Python interpreter.
- **Python runtime closure:** rebuilt or source-built Python packages needed by
  PyTorch, Triton, AITER, FlashAttention, TorchAO, Torch-MIGraphX, vLLM, and
  model support libraries.
- **Inference engines and backends:** vLLM, `llama.cpp` HIP/Vulkan, packaged
  FlashAttention lanes, and Lemonade server/app packages.
- **Convenience packages:** meta packages such as `lemonade` that describe an
  intended install set without hiding the package-specific update story.

## Maintainer Rules Of Thumb

- Treat `recipe.json` and the package README as durable package context, not as
  generated decoration.
- Keep reusable source changes in patch files beside the package.
- Put package-specific build and update rationale here; put cross-repo policy
  under `docs/`.
- After rendering or editing package metadata, verify the package-local docs
  still state the current desired source shape directly.
