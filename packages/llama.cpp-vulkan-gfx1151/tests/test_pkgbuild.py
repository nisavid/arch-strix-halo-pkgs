import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/llama.cpp-vulkan-gfx1151/PKGBUILD"
RECIPE_JSON = REPO_ROOT / "packages/llama.cpp-vulkan-gfx1151/recipe.json"
PACKAGE_PATCH_LINK = REPO_ROOT / "packages/llama.cpp-vulkan-gfx1151/0001-server-return-selected-token-logits.patch"
PATCH_FILE = REPO_ROOT / "patches/llama.cpp-common/0001-server-return-selected-token-logits.patch"

EXPECTED_VERSION = "b9222"
EXPECTED_COMMIT = "9a532ae4bab1b164052ce60a738f78538b421c66"
SELECTED_LOGITS_PATCH = "0001-server-return-selected-token-logits.patch"


def test_pkgbuild_tracks_recorded_llamacpp_release():
    text = PKGBUILD.read_text()
    assert f"pkgver={EXPECTED_VERSION}" in text
    assert EXPECTED_COMMIT in text
    assert "ggml-org/llama.cpp/archive/" in text
    assert 'rm -f "$pkgdir${install_root}/bin"/test-*' in text
    assert "$pkgdir$/opt" not in text


def test_pkgbuild_declares_spirv_headers_for_vulkan_backend():
    text = PKGBUILD.read_text()
    assert "spirv-headers" in text


def test_pkgbuild_applies_selected_token_logits_patch():
    text = PKGBUILD.read_text()
    assert SELECTED_LOGITS_PATCH in text
    assert PACKAGE_PATCH_LINK.is_symlink()
    assert PACKAGE_PATCH_LINK.resolve() == PATCH_FILE
    assert f'patch --dry-run -R -Np1 -i "$srcdir/{SELECTED_LOGITS_PATCH}"' in text
    assert f'patch -Np1 -i "$srcdir/{SELECTED_LOGITS_PATCH}"' in text
    assert text.index("prepare()") < text.index("build()")


def test_recipe_records_selected_token_logits_patch():
    recipe = json.loads(RECIPE_JSON.read_text())
    assert recipe["maintenance"]["source_patches"] == [SELECTED_LOGITS_PATCH]


def test_selected_token_logits_patch_exposes_generic_completion_contract():
    text = PATCH_FILE.read_text()
    assert '"token_logits"' in text
    assert "selected_token_logit_output" in text
    assert "populate_selected_token_logits" in text
    assert "max_token_logits = 1024" in text
    assert "completion_token_output::str_to_bytes(txt_valid)" in text
    assert "if (!slot.has_budget(params_base))" in text
    assert "backend_sampling &= task.params.token_logits.empty();" in text
    assert "llama_get_sampled_candidates_ith" not in text
    assert "bool found" not in text
    assert "zeroentropy" not in text.lower()
    assert "9454" not in text
