from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/lemonade-server/PKGBUILD"
CONF = (
    REPO_ROOT
    / "packages/lemonade-server/pkg/lemonade-server/etc/lemonade/conf.d/10-llamacpp-gfx1151.conf"
)
EXPECTED_LLAMACPP_VERSION = "b8881"
EXPECTED_RELEASE_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/tag/"
    f"{EXPECTED_LLAMACPP_VERSION}"
)


def test_pkgbuild_exports_system_managed_llamacpp_metadata():
    text = PKGBUILD.read_text()
    assert f"LEMONADE_LLAMACPP_ROCM_VERSION={EXPECTED_LLAMACPP_VERSION}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_VERSION={EXPECTED_LLAMACPP_VERSION}" in text
    assert f"LEMONADE_LLAMACPP_ROCM_RELEASE_URL={EXPECTED_RELEASE_URL}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_RELEASE_URL={EXPECTED_RELEASE_URL}" in text


def test_built_package_installs_system_managed_llamacpp_metadata():
    if not CONF.exists():
        pytest.skip("built lemonade-server package image is not present")

    text = CONF.read_text()
    assert f"LEMONADE_LLAMACPP_ROCM_VERSION={EXPECTED_LLAMACPP_VERSION}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_VERSION={EXPECTED_LLAMACPP_VERSION}" in text
    assert f"LEMONADE_LLAMACPP_ROCM_RELEASE_URL={EXPECTED_RELEASE_URL}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_RELEASE_URL={EXPECTED_RELEASE_URL}" in text
