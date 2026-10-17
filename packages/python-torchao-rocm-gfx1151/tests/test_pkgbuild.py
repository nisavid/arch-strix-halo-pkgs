from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-torchao-rocm-gfx1151/PKGBUILD"
README = REPO_ROOT / "packages/python-torchao-rocm-gfx1151/README.md"
RECIPE_JSON = REPO_ROOT / "packages/python-torchao-rocm-gfx1151/recipe.json"
PATCH = (
    REPO_ROOT
    / "packages/python-torchao-rocm-gfx1151/"
    / "0001-setup.py-honor-pytorch-rocm-arch.patch"
)
SWIZZLE_PATCH = (
    REPO_ROOT
    / "packages/python-torchao-rocm-gfx1151/"
    / "0003-swizzle-include-format-before-hip-runtime.patch"
)
PATCHES_DOC = REPO_ROOT / "docs/patches.md"
PT2E_PATCH = (
    REPO_ROOT
    / "packages/python-torchao-rocm-gfx1151/"
    / "0002-python-3.14-pt2e-union-aliases.patch"
)


def test_pkgbuild_uses_torch_2_12_compatible_torchao_lane():
    text = PKGBUILD.read_text()

    assert "pkgname=python-torchao-rocm-gfx1151" in text
    assert "pkgver=0.18.0" in text
    assert "pkgrel=1" in text
    assert "ao.git#tag=v0.18.0" in text
    assert "python-pytorch-opt-rocm-gfx1151" in text
    assert "VERSION_SUFFIX=" in text
    assert "ROCM_HOME=/opt/rocm" in text
    assert "PYTORCH_ROCM_ARCH=gfx1151" in text
    assert 'local _ccache_cache="$srcdir/.ccache/cache"' in text
    assert 'export CCACHE_DIR="${_ccache_cache}"' in text
    assert "patchelf" in text
    assert PATCH.name in text
    assert PT2E_PATCH.name not in text


def test_patch_makes_rocm_arch_configurable():
    text = PATCH.read_text()

    assert '--offload-arch=gfx942' in text
    assert '+        rocm_arch = os.getenv("PYTORCH_ROCM_ARCH", "gfx942")' in text
    assert '+        extra_compile_args["nvcc"].append(f"--offload-arch={rocm_arch}")' in text


def test_swizzle_patch_parses_format_before_hip_host_macros():
    # In plain C++ mode, hip/amd_detail/host_defines.h defines __noinline__
    # as an empty macro. GCC 16 <format> spells [[__gnu__::__noinline__]],
    # which then becomes [[__gnu__::]] when ATen reaches <chrono>.
    pkgbuild = PKGBUILD.read_text()
    patch = SWIZZLE_PATCH.read_text()

    assert SWIZZLE_PATCH.name in pkgbuild
    assert f'patch -Np1 -i "$srcdir/{SWIZZLE_PATCH.name}"' in pkgbuild
    assert "+++ b/torchao/csrc/rocm/swizzle/swizzle.cpp" in patch
    added = [line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")]
    body = [line for line in patch.splitlines() if line[:1] in " +" and not line.startswith("+++")]
    assert "#include <format>" in added
    assert body.index("+#include <format>") < body.index(" #include <hip/hip_runtime.h>")
    assert "rocm-systems/issues/9897" in patch


def test_swizzle_patch_records_provenance_and_drop_condition():
    for text in (README.read_text(), RECIPE_JSON.read_text(), PATCHES_DOC.read_text()):
        assert SWIZZLE_PATCH.name in text
        assert "rocm-systems/issues/9897" in text
        assert "pytorch/ao/pull/4697" in text


def test_pt2e_union_alias_patch_is_retired_upstream():
    # TorchAO 0.18.0 guards the typing.Union __module__ writes with
    # sys.version_info < (3, 14), so the local Python 3.14 patch is gone.
    readme = README.read_text()

    assert not PT2E_PATCH.exists()
    assert PT2E_PATCH.name not in RECIPE_JSON.read_text()
    assert "sys.version_info < (3, 14)" in readme


def test_package_docs_record_compatibility_and_runpath_story():
    readme = README.read_text()
    recipe = RECIPE_JSON.read_text()

    assert "0.18.0" in readme
    assert "torch 2.11.0+" in readme
    assert "python-pytorch-opt-rocm-gfx1151 2.12.0" in readme
    assert "VERSION_SUFFIX" in readme
    assert "ROCM_HOME=/opt/rocm" in readme
    assert "torch/lib" in readme
    assert "tools/torchao_vllm_smoke.py" in readme
    assert "Stored version is not the same as current default version" in readme
    assert "0.18.0" in recipe
    assert "ROCM_HOME=/opt/rocm" in recipe
    assert "tools/torchao_vllm_smoke.py" in recipe


def test_native_wheel_recipe_patch_metadata_avoids_private_build_paths():
    recipes = [
        REPO_ROOT / "packages/python-asyncpg-gfx1151/recipe.json",
        REPO_ROOT / "packages/python-duckdb-gfx1151/recipe.json",
        REPO_ROOT / "packages/python-numpy-gfx1151/recipe.json",
        REPO_ROOT / "packages/python-sentencepiece-gfx1151/recipe.json",
        REPO_ROOT / "packages/python-torchao-rocm-gfx1151/recipe.json",
        REPO_ROOT / "packages/python-zstandard-gfx1151/recipe.json",
    ]

    for recipe_path in recipes:
        text = recipe_path.read_text()
        for marker in ("${VLLM_DIR}", "/home/", "/mnt/", "/tmp/"):
            assert marker not in text, recipe_path
