from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKG_DIR = REPO_ROOT / "packages/python-vllm-rocm-gfx1151"
PATCH = PKG_DIR / "0013-speculators-dflash-config-parsing.patch"
PKGBUILD = PKG_DIR / "PKGBUILD"


def test_dflash_speculators_config_patch_is_packaged():
    patch_text = PATCH.read_text(encoding="utf-8")
    pkgbuild_text = PKGBUILD.read_text(encoding="utf-8")

    assert '@register_speculator("dflash")' in patch_text
    assert 'pre_trained_config["architectures"] = ["DFlashDraftModel"]' in patch_text
    assert 'pre_trained_config["dflash_config"]' in patch_text
    assert '"mask_token_id"' in patch_text
    assert '"target_layer_ids"' in patch_text
    assert "0013-speculators-dflash-config-parsing.patch" in pkgbuild_text
    assert (
        'grep -Fq \'def update_dflash(config_dict: dict, pre_trained_config: dict) -> None:\''
        in pkgbuild_text
    )
