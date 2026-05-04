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

ENGINE_STACK = {
    "stable-diffusion.cpp-vulkan-gfx1151": {
        "template": "stable-diffusion-cpp",
        "recipe_key": "stable_diffusion_cpp",
        "upstream_version": "r593.g3d6064b",
        "provides": [
            "stable-diffusion.cpp-vulkan-gfx1151",
            "stable-diffusion.cpp-vulkan",
        ],
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
        if package_name == "python-tokenizers-gfx1151":
            assert "export CARGO_HOME" not in pkgbuild
            assert recipe["policy"]["isolated_cargo_home"] is False
        if package_name == "python-safetensors-gfx1151":
            assert "Rust-backed Python extension" in readme
            assert "pure Python" not in readme
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


def test_pytorch_build_metadata_prefers_local_pyyaml_package() -> None:
    packages = tomllib.loads((REPO_ROOT / "policies/recipe-packages.toml").read_text())[
        "packages"
    ]
    policy = packages["python-pytorch-opt-rocm-gfx1151"]
    recipe = json.loads(
        (REPO_ROOT / "packages/python-pytorch-opt-rocm-gfx1151/recipe.json").read_text()
    )["policy"]
    pkgbuild = (
        REPO_ROOT / "packages/python-pytorch-opt-rocm-gfx1151/PKGBUILD"
    ).read_text()

    assert "python-pyyaml-gfx1151" in policy["depends"]
    assert "python-pyyaml-gfx1151" in policy["makedepends"]
    assert "python-yaml" not in policy["makedepends"]
    assert recipe["makedepends"] == policy["makedepends"]
    assert "python-pyyaml-gfx1151" in pkgbuild
    assert "python-yaml" not in pkgbuild


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
        if package_name == "python-frozenlist-gfx1151":
            assert recipe["policy"]["patches_dir"] == "patches/python-frozenlist-gfx1151"


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
        if package_name in {
            "python-accelerate-gfx1151",
            "python-compressed-tensors-gfx1151",
            "python-nvidia-ml-py-gfx1151",
        }:
            assert "arch=('any')" in pkgbuild
            assert "rocm-llvm-gfx1151" not in pkgbuild
            assert "_setup_compiler_env" not in pkgbuild
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


def test_blackcat_engine_stack_is_policy_managed() -> None:
    packages = tomllib.loads((REPO_ROOT / "policies/recipe-packages.toml").read_text())[
        "packages"
    ]

    for package_name, expected in ENGINE_STACK.items():
        policy = packages[package_name]
        assert policy["template"] == expected["template"]
        assert policy["recipe_key"] == expected["recipe_key"]
        assert policy["upstream_version"] == expected["upstream_version"]
        assert policy["provides"] == expected["provides"]
        assert set(policy["depends"]) >= {
            "aocl-libm-gfx1151",
            "gcc-libs",
            "glibc",
            "vulkan-icd-loader",
        }


def test_blackcat_engine_stack_rendered_output_exists() -> None:
    package_name = "stable-diffusion.cpp-vulkan-gfx1151"
    package_dir = REPO_ROOT / "packages" / package_name
    pkgbuild = (package_dir / "PKGBUILD").read_text()
    recipe = json.loads((package_dir / "recipe.json").read_text())
    readme = (package_dir / "README.md").read_text()

    assert f"pkgname={package_name}" in pkgbuild
    assert "pkgver=r593.g3d6064b" in pkgbuild
    assert "git submodule update --init --recursive" not in pkgbuild
    assert "ggml::git+https://github.com/ggml-org/ggml.git" in pkgbuild
    assert "sdcpp-webui::git+https://github.com/leejet/sdcpp-webui.git" in pkgbuild
    assert 'cp -a "$srcdir/ggml" ggml' in pkgbuild
    assert 'cp -a "$srcdir/sdcpp-webui" examples/server/frontend' in pkgbuild
    assert "0001-sdxl-clipg-prefix-mapping.patch" in pkgbuild
    assert "-DSD_VULKAN=ON" in pkgbuild
    assert "-DGGML_VULKAN_VALIDATE=OFF" in pkgbuild
    assert "sd-cli-vulkan-gfx1151" in pkgbuild
    assert "sd-server-vulkan-gfx1151" in pkgbuild
    assert 'patchelf --set-rpath "/usr/lib"' in pkgbuild
    assert r'patchelf --set-rpath "/usr/lib:${install_root}/lib"' not in pkgbuild
    assert recipe["policy"]["recipe_key"] == "stable_diffusion_cpp"
    assert "Blackcat" in readme
    assert "recursive git submodules" not in readme
    assert "prepare-time network submodule fetches" in readme
    assert "explicit package sources" in readme
    assert "recursive ggml" not in recipe["policy"]["recipe_notes_override"]
    assert "explicit package sources" in recipe["policy"]["recipe_notes_override"]
