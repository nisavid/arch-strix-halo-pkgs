# Hand-Maintained Packages

These package bases are maintained directly rather than generated from the
TheRock install tree.

They correspond to the parts of the Strix Halo recipe that apply source-level
patches, custom build flags, or post-build wheel repacking beyond the TheRock
split package family.

Use these files together:

- `manifest.toml`: package inventory and upstream sources
- `packages/<name>/recipe.json`: machine-readable maintenance metadata
- `packages/<name>/README.md`: human-readable update summary for the package

Most of these package directories are rendered from
`tools/render_recipe_scaffolds.py` plus `policies/recipe-packages.toml`.
Rerun the renderer whenever recipe notes, patch actions, package baselines, or
step assignments change so the package-local docs stay in sync with the policy.
