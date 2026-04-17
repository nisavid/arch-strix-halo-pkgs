import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools/recipe_repo.py"
SPEC = importlib.util.spec_from_file_location("recipe_repo", MODULE_PATH)
assert SPEC and SPEC.loader
recipe_repo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recipe_repo)


def make_recipe_root(root: Path, *, subdir: str = "strix-halo") -> Path:
    recipe_root = root.resolve()
    (recipe_root / subdir).mkdir(parents=True, exist_ok=True)
    return recipe_root


def test_explicit_recipe_root_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    packaging_root = tmp_path / "packaging"
    make_recipe_root(packaging_root / "upstream" / "ai-notes")
    env_root = make_recipe_root(tmp_path / "env-recipe")
    explicit_root = make_recipe_root(tmp_path / "explicit-recipe")
    monkeypatch.setenv(recipe_repo.RECIPE_ROOT_ENV_VAR, str(env_root))

    resolved = recipe_repo.resolve_recipe_root(
        str(explicit_root),
        packaging_root=packaging_root,
    )

    assert resolved == explicit_root.resolve()


def test_env_recipe_root_wins_when_cli_arg_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    packaging_root = tmp_path / "packaging"
    make_recipe_root(packaging_root / "upstream" / "ai-notes")
    env_root = make_recipe_root(tmp_path / "env-recipe")
    monkeypatch.setenv(recipe_repo.RECIPE_ROOT_ENV_VAR, str(env_root))

    resolved = recipe_repo.resolve_recipe_root(None, packaging_root=packaging_root)

    assert resolved == env_root.resolve()


def test_local_submodule_recipe_root_is_default(tmp_path: Path):
    packaging_root = tmp_path / "packaging"
    local_root = make_recipe_root(packaging_root / "upstream" / "ai-notes")

    resolved = recipe_repo.resolve_recipe_root(None, packaging_root=packaging_root)

    assert resolved == local_root.resolve()


def test_missing_recipe_root_raises_actionable_error(tmp_path: Path):
    packaging_root = tmp_path / "packaging"

    with pytest.raises(RuntimeError) as excinfo:
        recipe_repo.resolve_recipe_root(None, packaging_root=packaging_root)

    message = str(excinfo.value)
    assert "RECIPE_ROOT_NOT_FOUND" in message
    assert str(packaging_root / "upstream" / "ai-notes") in message
    assert recipe_repo.RECIPE_ROOT_ENV_VAR in message


def test_resolve_recipe_dir_requires_existing_subdir(tmp_path: Path):
    recipe_root = make_recipe_root(tmp_path / "ai-notes", subdir="strix-halo")

    resolved = recipe_repo.resolve_recipe_dir(recipe_root, "strix-halo")

    assert resolved == (recipe_root / "strix-halo").resolve()

    with pytest.raises(RuntimeError) as excinfo:
        recipe_repo.resolve_recipe_dir(recipe_root, "missing-subdir")

    message = str(excinfo.value)
    assert "RECIPE_SUBDIR_NOT_FOUND" in message
    assert "missing-subdir" in message
