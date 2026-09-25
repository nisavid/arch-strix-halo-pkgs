from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKG_DIR = REPO_ROOT / "packages/python-vllm-rocm-gfx1151"
PKGBUILD = PKG_DIR / "PKGBUILD"


def test_dflash_speculators_config_parser_is_upstream_in_current_vllm():
    pkgbuild_text = PKGBUILD.read_text(encoding="utf-8")

    assert "pkgver=0.30.0" in pkgbuild_text
    assert "0013-speculators-dflash-config-parsing.patch" not in pkgbuild_text
    # DFlash parsing is upstream code, so the source-patch sentinels do not
    # check it.
    assert "speculators/algos.py" not in pkgbuild_text
