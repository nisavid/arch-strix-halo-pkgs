import json
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "packages/python-duckdb-gfx1151"


def test_duckdb_recipe_package_is_policy_managed_native_wheel() -> None:
    packages = tomllib.loads((REPO_ROOT / "policies/recipe-packages.toml").read_text())[
        "packages"
    ]
    policy = packages["python-duckdb-gfx1151"]

    assert policy["recipe_key"] == "native_wheels"
    assert policy["template"] == "native-wheel-pypi"
    assert policy["upstream_version"] == "1.5.2"
    assert policy["authoritative_reference"] == "extra/python-duckdb"
    assert "cachyos-extra-znver4/python-duckdb" in policy["advisory_references"]
    assert policy["provides"] == ["python-duckdb"]
    assert policy["conflicts"] == ["python-duckdb"]
    assert "python-typing_extensions" in policy["depends"]
    assert policy["skip_dependency_check"] is True


def test_rendered_duckdb_pkgbuild_follows_native_wheel_lane() -> None:
    pkgbuild = (PACKAGE / "PKGBUILD").read_text()
    recipe = json.loads((PACKAGE / "recipe.json").read_text())
    readme = (PACKAGE / "README.md").read_text()

    assert "pkgname=python-duckdb-gfx1151" in pkgbuild
    assert "pkgver=1.5.2" in pkgbuild
    assert "source=(https://files.pythonhosted.org/packages/source/d/duckdb/duckdb-1.5.2.tar.gz)" in pkgbuild
    assert "python -m build --wheel --no-isolation --skip-dependency-check" in pkgbuild
    assert "provides=(python-duckdb)" in pkgbuild
    assert "conflicts=(python-duckdb)" in pkgbuild
    assert "python-typing_extensions" in pkgbuild

    assert recipe["recipe"]["notes"].startswith(
        "Builds and installs numpy, sentencepiece, zstandard, asyncpg, duckdb"
    )
    assert "Embedded OLAP engine for local analytics and parquet scans" in readme
