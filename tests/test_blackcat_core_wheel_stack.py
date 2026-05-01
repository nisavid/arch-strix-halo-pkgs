import json
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

CORE_STACK = {
    "python-pydantic-core-gfx1151": {
        "template": "rust-wheel-pypi",
        "recipe_key": "rust_wheels",
        "upstream_version": "2.41.5",
        "provides": ["python-pydantic-core"],
        "consumer_dep": "python-pydantic-core-gfx1151",
    },
    "python-tokenizers-gfx1151": {
        "template": "rust-wheel-pypi",
        "recipe_key": "rust_wheels",
        "upstream_version": "0.22.2",
        "provides": ["python-tokenizers"],
        "consumer_dep": "python-tokenizers-gfx1151",
    },
    "python-safetensors-gfx1151": {
        "template": "rust-wheel-pypi",
        "recipe_key": "rust_wheels",
        "upstream_version": "0.7.0",
        "provides": ["python-safetensors"],
        "consumer_dep": "python-safetensors-gfx1151",
    },
    "python-pyyaml-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "6.0.3",
        "provides": ["python-yaml", "python-pyyaml"],
        "consumer_dep": "python-pyyaml-gfx1151",
    },
    "python-psutil-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "7.2.2",
        "provides": ["python-psutil"],
        "consumer_dep": "python-psutil-gfx1151",
    },
    "python-pillow-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "12.2.0",
        "provides": ["python-pillow"],
        "consumer_dep": "python-pillow-gfx1151",
    },
}


def test_core_blackcat_wheel_stack_is_policy_managed() -> None:
    packages = tomllib.loads((REPO_ROOT / "policies/recipe-packages.toml").read_text())[
        "packages"
    ]

    for package_name, expected in CORE_STACK.items():
        policy = packages[package_name]
        assert policy["template"] == expected["template"]
        assert policy["recipe_key"] == expected["recipe_key"]
        assert policy["upstream_version"] == expected["upstream_version"]
        assert policy["provides"] == expected["provides"]
        assert set(policy["conflicts"]) >= set(expected["provides"])
        assert "python-gfx1151" in policy["depends"]


def test_core_blackcat_wheel_stack_rendered_outputs_exist() -> None:
    for package_name, expected in CORE_STACK.items():
        package_dir = REPO_ROOT / "packages" / package_name
        pkgbuild = (package_dir / "PKGBUILD").read_text()
        recipe = json.loads((package_dir / "recipe.json").read_text())
        readme = (package_dir / "README.md").read_text()

        assert f"pkgname={package_name}" in pkgbuild
        assert f"pkgver={expected['upstream_version']}" in pkgbuild
        assert f"provides=({' '.join(expected['provides'])})" in pkgbuild
        assert recipe["policy"]["recipe_key"] == expected["recipe_key"]
        assert "Blackcat" in readme


def test_consumers_prefer_local_core_stack_packages() -> None:
    packages = tomllib.loads((REPO_ROOT / "policies/recipe-packages.toml").read_text())[
        "packages"
    ]
    transformers = json.loads(
        (REPO_ROOT / "packages/python-transformers-gfx1151/recipe.json").read_text()
    )["policy"]
    mistral_common = json.loads(
        (REPO_ROOT / "packages/python-mistral-common-gfx1151/recipe.json").read_text()
    )["policy"]

    assert "python-safetensors-gfx1151" in transformers["depends"]
    assert "python-tokenizers-gfx1151" in transformers["depends"]
    assert "python-pyyaml-gfx1151" in transformers["depends"]
    assert "python-psutil-gfx1151" in packages["python-vllm-rocm-gfx1151"]["depends"]
    assert "python-pillow-gfx1151" in mistral_common["depends"]
    assert "python-pillow-gfx1151" in packages["python-torchvision-rocm-gfx1151"]["depends"]
