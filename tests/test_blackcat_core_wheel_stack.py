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

SERVICE_STACK = {
    "python-watchfiles-gfx1151": {
        "template": "rust-wheel-pypi",
        "recipe_key": "rust_wheels",
        "upstream_version": "1.1.1",
        "provides": ["python-watchfiles"],
        "consumer_dep": "python-watchfiles-gfx1151",
    },
    "python-uvloop-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "0.22.1",
        "provides": ["python-uvloop"],
        "consumer_dep": "python-uvloop-gfx1151",
    },
    "python-httptools-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "0.7.1",
        "provides": ["python-httptools"],
        "consumer_dep": "python-httptools-gfx1151",
    },
    "python-msgspec-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "0.21.1",
        "provides": ["python-msgspec"],
        "consumer_dep": "python-msgspec-gfx1151",
    },
    "python-aiohttp-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "3.13.5",
        "provides": ["python-aiohttp"],
        "consumer_dep": "python-aiohttp-gfx1151",
    },
    "python-multidict-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "6.7.1",
        "provides": ["python-multidict"],
        "consumer_dep": "python-multidict-gfx1151",
    },
    "python-yarl-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "1.23.0",
        "provides": ["python-yarl"],
        "consumer_dep": "python-yarl-gfx1151",
    },
    "python-frozenlist-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "1.8.0",
        "provides": ["python-frozenlist"],
        "consumer_dep": "python-frozenlist-gfx1151",
    },
}

TOOLING_STACK = {
    "python-accelerate-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "1.12.0",
        "provides": ["python-accelerate"],
        "consumer_dep": "python-accelerate-gfx1151",
    },
    "python-auto-round-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "0.10.2",
        "provides": ["python-auto-round"],
        "consumer_dep": "python-auto-round-gfx1151",
    },
    "python-compressed-tensors-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "0.15.0.1",
        "provides": ["python-compressed-tensors"],
        "consumer_dep": "python-compressed-tensors-gfx1151",
    },
    "python-nvidia-ml-py-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "13.590.48",
        "provides": ["python-nvidia-ml-py"],
        "consumer_dep": "python-nvidia-ml-py-gfx1151",
    },
    "python-llmcompressor-gfx1151": {
        "template": "native-wheel-pypi",
        "recipe_key": "native_wheels",
        "upstream_version": "0.10.0.1",
        "provides": ["python-llmcompressor"],
        "consumer_dep": "python-llmcompressor-gfx1151",
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


def test_blackcat_service_wheel_stack_is_policy_managed() -> None:
    packages = tomllib.loads((REPO_ROOT / "policies/recipe-packages.toml").read_text())[
        "packages"
    ]

    for package_name, expected in SERVICE_STACK.items():
        policy = packages[package_name]
        assert policy["template"] == expected["template"]
        assert policy["recipe_key"] == expected["recipe_key"]
        assert policy["upstream_version"] == expected["upstream_version"]
        assert policy["provides"] == expected["provides"]
        assert set(policy["conflicts"]) >= set(expected["provides"])
        assert "python-gfx1151" in policy["depends"]


def test_blackcat_service_wheel_stack_rendered_outputs_exist() -> None:
    for package_name, expected in SERVICE_STACK.items():
        package_dir = REPO_ROOT / "packages" / package_name
        pkgbuild = (package_dir / "PKGBUILD").read_text()
        recipe = json.loads((package_dir / "recipe.json").read_text())
        readme = (package_dir / "README.md").read_text()

        assert f"pkgname={package_name}" in pkgbuild
        assert f"pkgver={expected['upstream_version']}" in pkgbuild
        assert f"provides=({' '.join(expected['provides'])})" in pkgbuild
        assert recipe["policy"]["recipe_key"] == expected["recipe_key"]
        assert "Blackcat" in readme


def test_service_consumers_prefer_local_blackcat_packages() -> None:
    packages = tomllib.loads((REPO_ROOT / "policies/recipe-packages.toml").read_text())[
        "packages"
    ]
    vllm_deps = set(packages["python-vllm-rocm-gfx1151"]["depends"])
    aiohttp_deps = set(packages["python-aiohttp-gfx1151"]["depends"])
    yarl_deps = set(packages["python-yarl-gfx1151"]["depends"])

    assert "python-watchfiles-gfx1151" in vllm_deps
    assert "python-uvloop-gfx1151" in vllm_deps
    assert "python-httptools-gfx1151" in vllm_deps
    assert "python-msgspec-gfx1151" in vllm_deps
    assert "python-aiohttp-gfx1151" in vllm_deps
    assert "python-frozenlist-gfx1151" in aiohttp_deps
    assert "python-multidict-gfx1151" in aiohttp_deps
    assert "python-yarl-gfx1151" in aiohttp_deps
    assert "python-multidict-gfx1151" in yarl_deps


def test_blackcat_tooling_wheel_stack_is_policy_managed() -> None:
    packages = tomllib.loads((REPO_ROOT / "policies/recipe-packages.toml").read_text())[
        "packages"
    ]

    for package_name, expected in TOOLING_STACK.items():
        policy = packages[package_name]
        assert policy["template"] == expected["template"]
        assert policy["recipe_key"] == expected["recipe_key"]
        assert policy["upstream_version"] == expected["upstream_version"]
        assert policy["provides"] == expected["provides"]
        assert set(policy["conflicts"]) >= set(expected["provides"])
        assert "python-gfx1151" in policy["depends"]


def test_blackcat_tooling_wheel_stack_rendered_outputs_exist() -> None:
    for package_name, expected in TOOLING_STACK.items():
        package_dir = REPO_ROOT / "packages" / package_name
        pkgbuild = (package_dir / "PKGBUILD").read_text()
        recipe = json.loads((package_dir / "recipe.json").read_text())
        readme = (package_dir / "README.md").read_text()

        assert f"pkgname={package_name}" in pkgbuild
        assert f"pkgver={expected['upstream_version']}" in pkgbuild
        assert f"provides=({' '.join(expected['provides'])})" in pkgbuild
        assert recipe["policy"]["recipe_key"] == expected["recipe_key"]
        assert "Blackcat" in readme


def test_llmcompressor_closure_prefers_local_tooling_packages() -> None:
    packages = tomllib.loads((REPO_ROOT / "policies/recipe-packages.toml").read_text())[
        "packages"
    ]
    llmcompressor_deps = set(packages["python-llmcompressor-gfx1151"]["depends"])

    assert "python-accelerate-gfx1151" in llmcompressor_deps
    assert "python-auto-round-gfx1151" in llmcompressor_deps
    assert "python-compressed-tensors-gfx1151" in llmcompressor_deps
    assert "python-nvidia-ml-py-gfx1151" in llmcompressor_deps
    assert "python-transformers-gfx1151" in llmcompressor_deps
    assert "python-pytorch-opt-rocm-gfx1151" in llmcompressor_deps
