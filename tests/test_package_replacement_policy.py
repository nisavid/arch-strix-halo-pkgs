import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_recipe_packages_record_known_replacements() -> None:
    packages = tomllib.loads((REPO_ROOT / "policies/recipe-packages.toml").read_text())[
        "packages"
    ]

    assert set(packages["python-gfx1151"]["replaces"]) >= {
        "python",
        "python3",
        "python-externally-managed",
    }
    assert packages["lemonade-app"]["replaces"] == ["lemonade-desktop"]


def test_therock_packages_record_known_replacements() -> None:
    packages = tomllib.loads((REPO_ROOT / "policies/therock-packages.toml").read_text())[
        "packages"
    ]

    assert "hsakmt-roct" in packages["hsa-rocr-gfx1151"]["provides"]
    assert packages["hsa-rocr-gfx1151"]["replaces"] == ["hsakmt-roct"]
    assert packages["hip-runtime-amd-gfx1151"]["replaces"] == ["hip"]
    assert packages["hsa-amd-aqlprofile-gfx1151"]["replaces"] == [
        "hsa-amd-aqlprofile-bin"
    ]
    assert packages["magma-gfx1151"]["replaces"] == ["magma-hip", "hipmagma"]
