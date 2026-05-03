from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKG_DIR = REPO_ROOT / "packages/python-vllm-rocm-gfx1151"
PKGBUILD = PKG_DIR / "PKGBUILD"


def test_dflash_speculators_config_parser_is_upstream_in_vllm_0_20():
    pkgbuild_text = PKGBUILD.read_text(encoding="utf-8")

    assert "pkgver=0.20.1" in pkgbuild_text
    assert "0013-speculators-dflash-config-parsing.patch" not in pkgbuild_text
    assert (
        'grep -Fq \'def update_dflash(config_dict: dict, pre_trained_config: dict) -> None:\''
        in pkgbuild_text
    )
