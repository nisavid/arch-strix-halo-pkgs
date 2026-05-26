from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/lemonade-server/PKGBUILD"
SYSTEM_BACKEND_PATCH = (
    REPO_ROOT
    / "packages/lemonade-server/0002-llamacpp-external-backends-are-system-managed.patch"
)
SYSTEM_METADATA_PATCH = (
    REPO_ROOT
    / "packages/lemonade-server/0004-system-managed-llamacpp-metadata.patch"
)
CONF = (
    REPO_ROOT
    / "packages/lemonade-server/pkg/lemonade-server/etc/lemonade/conf.d/10-llamacpp-gfx1151.conf"
)
PKGINFO = REPO_ROOT / "packages/lemonade-server/pkg/lemonade-server/.PKGINFO"
LLAMACPP_HIP_PKGBUILD = REPO_ROOT / "packages/llama.cpp-hip-gfx1151/PKGBUILD"
SERVICE = (
    REPO_ROOT
    / "packages/lemonade-server/pkg/lemonade-server/usr/lib/systemd/system/lemond.service"
)
OLD_SERVICE = (
    REPO_ROOT
    / "packages/lemonade-server/pkg/lemonade-server/usr/lib/systemd/system/lemonade-server.service"
)
SOURCE_TREE = REPO_ROOT / "packages/lemonade-server/src/lemonade"


def _pkgbuild_value(path, key):
    prefix = f"{key}="
    for line in path.read_text().splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip("'\"")
    raise AssertionError(f"{key} not found in {path}")


EXPECTED_LLAMACPP_VERSION = _pkgbuild_value(LLAMACPP_HIP_PKGBUILD, "pkgver")
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
    assert "+        json config = utils::JsonUtils::merge(defaults, env_overlay);" in text
    assert "+        save(cache_dir, repaired);" in text
    assert "+        return repaired;" in text
    assert "return utils::JsonUtils::merge(defaults, env_overlay);" in text
    assert (
        "json merged = utils::JsonUtils::merge(utils::JsonUtils::merge(defaults, loaded), env_overlay);"
        in text
    )


def test_system_backend_patch_keeps_migration_overlay_sparse():
    text = SYSTEM_BACKEND_PATCH.read_text()

    assert "+    return overlay;" in text
    assert "-    return utils::JsonUtils::merge(defaults, overlay);" in text
    assert "0006-keep-env-migration-overlay-sparse.patch" not in PKGBUILD.read_text()


def test_system_backend_patch_reuses_external_backend_lookup():
    text = SYSTEM_BACKEND_PATCH.read_text()

    assert "find_system_managed_external_backend" in text
    assert "if (!external_binary.empty())" in text
    assert "is_system_managed_external_backend" not in text


def test_system_backend_metadata_overrides_require_external_backend():
    text = SYSTEM_METADATA_PATCH.read_text()

    assert 'if (!is_system_managed_external_backend(recipe, backend))' in text
    assert "get_system_managed_backend_version_override" in text
    assert "get_system_managed_backend_release_url_override" in text


def test_backend_lifecycle_fix_lives_in_pinned_fork_source():
    text = PKGBUILD.read_text()

    assert "b608a74d0604f96786de59d65cb0ba27b05db0c6" in text
    assert "0006-keep-llamacpp-backends-alive-after-threaded-loads.patch" not in text


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


def test_prepared_source_contains_zerank_selected_logit_adapter():
    if not SOURCE_TREE.exists():
        pytest.skip("prepared lemonade source is not present")

    server_models = SOURCE_TREE / "src/cpp/resources/server_models.json"
    adapter = SOURCE_TREE / "src/cpp/server/backends/llamacpp_reranking_adapter.cpp"
    adapter_header = (
        SOURCE_TREE / "src/cpp/include/lemon/backends/llamacpp_reranking_adapter.h"
    )
    for path in (server_models, adapter, adapter_header):
        if not path.exists():
            pytest.skip("prepared lemonade source is incomplete")

    models_text = server_models.read_text()
    adapter_text = adapter.read_text()
    header_text = adapter_header.read_text()

    assert '"zerank-2-GGUF"' in models_text
    assert '"llamacpp_reranking_adapter": "zeroentropy-logit-score"' in models_text
    assert '"llamacpp_reranking_true_token_id": 9454' in models_text
    assert '"llamacpp_reranking_logit_scale": 5.0' in models_text
    assert "ZEROENTROPY_LOGIT_SCORE_ADAPTER" in header_text
    assert "token_logits" in adapter_text
