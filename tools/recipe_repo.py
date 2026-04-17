from __future__ import annotations

import os
from pathlib import Path


RECIPE_ROOT_ENV_VAR = "STRIX_HALO_RECIPE_ROOT"
DEFAULT_RECIPE_SUBMODULE = Path("upstream") / "ai-notes"


def default_recipe_root(packaging_root: Path) -> Path:
    return (packaging_root / DEFAULT_RECIPE_SUBMODULE).resolve()


def resolve_recipe_root(recipe_root: str | None, *, packaging_root: Path) -> Path:
    if recipe_root:
        resolved = Path(recipe_root).expanduser().resolve()
    else:
        env_recipe_root = os.environ.get(RECIPE_ROOT_ENV_VAR)
        if env_recipe_root:
            resolved = Path(env_recipe_root).expanduser().resolve()
        else:
            resolved = default_recipe_root(packaging_root)

    if not resolved.is_dir():
        raise RuntimeError(
            "RECIPE_ROOT_NOT_FOUND: expected a checked-out ai-notes recipe repo at "
            f"{resolved}. Pass --recipe-root, set {RECIPE_ROOT_ENV_VAR}, or initialize "
            f"the repo-local submodule at {default_recipe_root(packaging_root)}."
        )
    return resolved


def resolve_recipe_dir(recipe_root: Path, recipe_subdir: str) -> Path:
    recipe_dir = (recipe_root / recipe_subdir).resolve()
    if not recipe_dir.is_dir():
        raise RuntimeError(
            "RECIPE_SUBDIR_NOT_FOUND: expected recipe subdir "
            f"{recipe_subdir!r} under {recipe_root}."
        )
    return recipe_dir
