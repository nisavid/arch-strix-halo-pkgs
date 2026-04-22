import json
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE = REPO_ROOT / "packages/python-flash-attn-rocm-gfx1151"
PKGBUILD = PACKAGE / "PKGBUILD"
README = PACKAGE / "README.md"
RECIPE_JSON = PACKAGE / "recipe.json"
FRESHNESS_POLICY = REPO_ROOT / "policies/package-freshness.toml"
SKIP_AITER_PATCH = PACKAGE / "0001-skip-bundled-aiter-install.patch"
AMDSMI_PATCH = PACKAGE / "0002-import-amdsmi-before-torch.patch"
SYSTEM_TRITON_PATCH = PACKAGE / "0003-use-system-triton-package.patch"


def test_pkgbuild_tracks_rocm_flash_attention_triton_experiment():
    text = PKGBUILD.read_text(encoding="utf-8")

    assert "pkgname=python-flash-attn-rocm-gfx1151" in text
    assert "pkgver=2.8.4" in text
    assert "3f94643fb41bcedded28c85185a8e11d42ef1592" in text
    assert "url=https://github.com/ROCm/flash-attention" in text
    assert "FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE" in text
    assert "FLASH_ATTENTION_SKIP_CUDA_BUILD=TRUE" in text
    assert "FLASH_ATTENTION_FORCE_BUILD=TRUE" in text
    assert "GPU_ARCHS=gfx1151" in text
    assert "pip wheel . --no-build-isolation --no-deps" in text
    assert "python -m installer --destdir=\"$pkgdir\"" in text


def test_pkgbuild_uses_repo_owned_rocm_runtime_instead_of_bundled_deps():
    text = PKGBUILD.read_text(encoding="utf-8")

    for dependency in [
        "python-gfx1151",
        "python-pytorch-opt-rocm-gfx1151",
        "python-triton-gfx1151",
        "python-amd-aiter-gfx1151",
        "python-einops",
        "python-packaging",
    ]:
        assert dependency in text

    assert "pip install" not in text
    assert "third_party/aiter" not in text
    assert "triton==3.5.1" not in text


def test_patch_carry_records_rocm_runtime_boundaries():
    skip_aiter = SKIP_AITER_PATCH.read_text(encoding="utf-8")
    amdsmi = AMDSMI_PATCH.read_text(encoding="utf-8")
    system_triton = SYSTEM_TRITON_PATCH.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    recipe = json.loads(RECIPE_JSON.read_text(encoding="utf-8"))

    assert "skip bundled AITER install" in skip_aiter
    assert "third_party/aiter" in skip_aiter
    assert "import amdsmi" in amdsmi
    assert "triton==3.5.1" in system_triton
    assert '"triton"' in system_triton
    assert "FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE" in readme
    assert "FLASH_ATTENTION_TRITON_AMD_AUTOTUNE=TRUE" in readme
    assert "python-amd-aiter-gfx1151" in readme
    assert recipe["package_name"] == "python-flash-attn-rocm-gfx1151"
    assert recipe["upstream"]["commit"] == "3f94643fb41bcedded28c85185a8e11d42ef1592"
    assert "0001-skip-bundled-aiter-install.patch" in recipe["source_patches"]
    assert "0002-import-amdsmi-before-torch.patch" in recipe["source_patches"]
    assert "0003-use-system-triton-package.patch" in recipe["source_patches"]


def test_freshness_policy_covers_flash_attention_branch():
    policy = tomllib.loads(FRESHNESS_POLICY.read_text(encoding="utf-8"))
    family = policy["families"]["flash_attention"]

    assert family["packages"] == ["python-flash-attn-rocm-gfx1151"]
    assert family["workflow"] == "upstream_source_update"
    assert family["checks"] == [
        {
            "id": "main-perf",
            "role": "primary",
            "kind": "git_ref",
            "repo": "https://github.com/ROCm/flash-attention.git",
            "ref": "refs/heads/main_perf",
            "recorded": "3f94643fb41bcedded28c85185a8e11d42ef1592",
            "comparison": "sha",
        }
    ]
