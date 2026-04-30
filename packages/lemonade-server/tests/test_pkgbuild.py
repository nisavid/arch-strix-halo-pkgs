from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/lemonade-server/PKGBUILD"
SYSTEM_BACKEND_PATCH = (
    REPO_ROOT
    / "packages/lemonade-server/0002-llamacpp-external-backends-are-system-managed.patch"
)
CONF = (
    REPO_ROOT
    / "packages/lemonade-server/pkg/lemonade-server/etc/lemonade/conf.d/10-llamacpp-gfx1151.conf"
)
PKGINFO = REPO_ROOT / "packages/lemonade-server/pkg/lemonade-server/.PKGINFO"
SERVICE = (
    REPO_ROOT
    / "packages/lemonade-server/pkg/lemonade-server/usr/lib/systemd/system/lemond.service"
)
OLD_SERVICE = (
    REPO_ROOT
    / "packages/lemonade-server/pkg/lemonade-server/usr/lib/systemd/system/lemonade-server.service"
)
EXPECTED_LLAMACPP_VERSION = "b8966"
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


def test_pkgbuild_keeps_upstream_lemond_service_install():
    text = PKGBUILD.read_text()
    assert "DESTDIR=\"$pkgdir\" cmake --install" in text
    assert "lemonade-server.service" not in text


def test_system_backend_patch_applies_env_overlay_without_config_file():
    text = SYSTEM_BACKEND_PATCH.read_text()

    assert "json env_overlay = migrate_from_env(defaults);" in text
    assert "return utils::JsonUtils::merge(defaults, env_overlay);" in text
    assert (
        "return utils::JsonUtils::merge(utils::JsonUtils::merge(defaults, loaded), env_overlay);"
        in text
    )


def _current_pkgbuild_version():
    values = {}
    for line in PKGBUILD.read_text().splitlines():
        if line.startswith(("pkgver=", "pkgrel=")):
            key, value = line.split("=", 1)
            values[key] = value.strip("'\"")
    return f"{values['pkgver']}-{values['pkgrel']}"


def _built_package_version():
    if not PKGINFO.exists():
        return None
    for line in PKGINFO.read_text().splitlines():
        if line.startswith("pkgver = "):
            return line.removeprefix("pkgver = ")
    return None


def test_built_package_installs_system_managed_llamacpp_metadata():
    if not CONF.exists():
        pytest.skip("built lemonade-server package image is not present")
    if _built_package_version() != _current_pkgbuild_version():
        pytest.skip("built lemonade-server package image is stale")

    text = CONF.read_text()
    assert f"LEMONADE_LLAMACPP_ROCM_VERSION={EXPECTED_LLAMACPP_VERSION}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_VERSION={EXPECTED_LLAMACPP_VERSION}" in text
    assert f"LEMONADE_LLAMACPP_ROCM_RELEASE_URL={EXPECTED_RELEASE_URL}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_RELEASE_URL={EXPECTED_RELEASE_URL}" in text


def test_built_package_installs_renamed_lemond_service():
    if _built_package_version() != _current_pkgbuild_version():
        pytest.skip("built lemonade-server package image is stale or not present")

    assert SERVICE.exists()
    assert not OLD_SERVICE.exists()
