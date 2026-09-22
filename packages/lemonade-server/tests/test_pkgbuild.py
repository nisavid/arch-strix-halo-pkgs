import json
from pathlib import Path
import re
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from recipe_policy import load_recipe_policy  # noqa: E402


PKGBUILD = REPO_ROOT / "packages/lemonade-server/PKGBUILD"
RECIPE_POLICY = REPO_ROOT / "policies/recipe-packages.toml"
SYSTEM_BACKEND_PATCH = (
    REPO_ROOT
    / "packages/lemonade-server/0002-llamacpp-external-backends-are-system-managed.patch"
)
SYSTEM_METADATA_PATCH = (
    REPO_ROOT
    / "packages/lemonade-server/0004-system-managed-llamacpp-metadata.patch"
)
PKG_ROOT = REPO_ROOT / "packages/lemonade-server/pkg/lemonade-server"
CONF = PKG_ROOT / "etc/lemonade/conf.d/10-llamacpp-gfx1151.conf"
DISTRO_DEFAULTS = PKG_ROOT / "usr/share/lemonade/defaults.json"
NO_REMOTE_FETCH_DROPIN = (
    PKG_ROOT / "usr/lib/systemd/system/lemond.service.d/20-no-remote-model-fetch.conf"
)
PKGINFO = PKG_ROOT / ".PKGINFO"
LLAMACPP_HIP_PKGBUILD = REPO_ROOT / "packages/llama.cpp-hip-gfx1151/PKGBUILD"
SERVICE = PKG_ROOT / "usr/lib/systemd/system/lemond.service"
OLD_SERVICE = PKG_ROOT / "usr/lib/systemd/system/lemonade-server.service"
SOURCE_TREE = REPO_ROOT / "packages/lemonade-server/src/lemonade"

HIP_SERVER = "/usr/bin/llama-server-hip-gfx1151"
VULKAN_SERVER = "/usr/bin/llama-server-vulkan-gfx1151"
BLACKHOLE_ENDPOINT = "http://127.0.0.1:9"


def _pkgbuild_value(path, key):
    prefix = f"{key}="
    for line in path.read_text().splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip("'\"")
    raise AssertionError(f"{key} not found in {path}")


def _heredoc(text, target):
    match = re.search(
        rf'install -Dm644 /dev/stdin "\$pkgdir{re.escape(target)}" <<\'EOF\'\n(.*?)\nEOF\n',
        text,
        re.DOTALL,
    )
    assert match, f"no heredoc install for {target}"
    return match.group(1)


EXPECTED_LLAMACPP_VERSION = _pkgbuild_value(LLAMACPP_HIP_PKGBUILD, "pkgver")
EXPECTED_RELEASE_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/tag/"
    f"{EXPECTED_LLAMACPP_VERSION}"
)
LEMONADE_PIN = load_recipe_policy(RECIPE_POLICY)["source_pins"]["lemonade"]


def test_pkgbuild_exports_system_managed_llamacpp_metadata():
    text = _heredoc(PKGBUILD.read_text(), "/etc/lemonade/conf.d/10-llamacpp-gfx1151.conf")
    assert f"LEMONADE_LLAMACPP_ROCM_BIN={HIP_SERVER}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_BIN={VULKAN_SERVER}" in text
    assert f"LEMONADE_LLAMACPP_ROCM_VERSION={EXPECTED_LLAMACPP_VERSION}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_VERSION={EXPECTED_LLAMACPP_VERSION}" in text
    assert f"LEMONADE_LLAMACPP_ROCM_RELEASE_URL={EXPECTED_RELEASE_URL}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_RELEASE_URL={EXPECTED_RELEASE_URL}" in text
    assert "_LABEL=" not in text


def test_pkgbuild_keeps_upstream_lemond_service_install():
    text = PKGBUILD.read_text()
    assert "DESTDIR=\"$pkgdir\" cmake --install" in text
    assert "lemonade-server.service" not in text


def test_pkgbuild_preserves_secrets_drop_in_across_upgrades():
    text = PKGBUILD.read_text()

    assert "backup=(etc/lemonade/conf.d/zz-secrets.conf)\n" in text
    assert "10-llamacpp-gfx1151.conf" not in _pkgbuild_value(PKGBUILD, "backup")


def test_pkgbuild_skips_upstream_test_binaries():
    assert "-DBUILD_TESTING=OFF" in PKGBUILD.read_text()


def test_pkgbuild_drops_web_app_metainfo_with_its_desktop_entry():
    text = PKGBUILD.read_text()

    assert '"$pkgdir/usr/share/applications"' in text
    assert '"$pkgdir/usr/share/metainfo"' in text


def test_pkgbuild_ships_offline_distro_defaults():
    defaults = json.loads(_heredoc(PKGBUILD.read_text(), "/usr/share/lemonade/defaults.json"))

    assert defaults == {
        "offline": True,
        "no_fetch_executables": True,
        "llamacpp": {
            "args": "--no-mmap",
            "backend": "rocm",
            "prefer_system": False,
            "rocm_bin": HIP_SERVER,
            "vulkan_bin": VULKAN_SERVER,
        },
    }


def test_distro_defaults_leave_host_binding_and_auth_to_the_host():
    defaults = json.loads(_heredoc(PKGBUILD.read_text(), "/usr/share/lemonade/defaults.json"))

    for key in ("host", "port", "broadcast", "no_broadcast"):
        assert key not in defaults
    assert not any("key" in key.lower() for key in defaults)


def test_pkgbuild_blackholes_remote_model_endpoints_for_lemond():
    text = _heredoc(
        PKGBUILD.read_text(),
        "/usr/lib/systemd/system/lemond.service.d/20-no-remote-model-fetch.conf",
    )

    assert text.splitlines() == [
        "[Service]",
        f"Environment=HF_ENDPOINT={BLACKHOLE_ENDPOINT}",
        f"Environment=MODELSCOPE_ENDPOINT={BLACKHOLE_ENDPOINT}",
        f"Environment=MODEL_ENDPOINT={BLACKHOLE_ENDPOINT}",
    ]


def test_system_backend_patch_reuses_external_backend_lookup():
    text = SYSTEM_BACKEND_PATCH.read_text()

    assert "find_system_managed_external_backend" in text
    assert "if (!external_binary.empty())" in text
    assert "is_system_managed_external_backend" not in text


def test_system_backend_patch_leaves_config_loading_to_upstream():
    text = SYSTEM_BACKEND_PATCH.read_text()

    assert "src/cpp/server/config_file.cpp" not in text
    assert "env_overlay" not in text


def test_system_backend_metadata_overrides_require_external_backend():
    text = SYSTEM_METADATA_PATCH.read_text()

    assert 'if (!is_system_managed_external_backend(recipe, backend))' in text
    assert "get_system_managed_backend_version_override" in text
    assert "get_system_managed_backend_release_url_override" in text


def test_pkgbuild_builds_the_pinned_fork_commit():
    text = PKGBUILD.read_text()

    assert re.fullmatch(r"[0-9a-f]{40}", LEMONADE_PIN)
    assert (
        f"'lemonade::git+https://github.com/nisavid/lemonade.git#commit={LEMONADE_PIN}'"
        in text
    )
    assert "0006-keep-llamacpp-backends-alive-after-threaded-loads.patch" not in text


def test_pkgbuild_checksums_every_local_patch():
    sums = _pkgbuild_value(PKGBUILD, "sha256sums").strip("()").split()

    assert sums[0] == "SKIP"
    assert len(sums) == 5
    assert all(re.fullmatch(r"[0-9a-f]{64}", item) for item in sums[1:])


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


def _require_current_package_image():
    if _built_package_version() != _current_pkgbuild_version():
        pytest.skip("built lemonade-server package image is stale or not present")


def test_built_package_installs_system_managed_llamacpp_metadata():
    _require_current_package_image()

    text = CONF.read_text()
    assert f"LEMONADE_LLAMACPP_ROCM_VERSION={EXPECTED_LLAMACPP_VERSION}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_VERSION={EXPECTED_LLAMACPP_VERSION}" in text
    assert f"LEMONADE_LLAMACPP_ROCM_RELEASE_URL={EXPECTED_RELEASE_URL}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_RELEASE_URL={EXPECTED_RELEASE_URL}" in text


def test_built_package_installs_renamed_lemond_service():
    _require_current_package_image()

    assert SERVICE.exists()
    assert not OLD_SERVICE.exists()


def test_built_package_installs_offline_defaults_and_endpoint_drop_in():
    _require_current_package_image()

    defaults = json.loads(DISTRO_DEFAULTS.read_text())
    assert defaults["offline"] is True
    assert defaults["no_fetch_executables"] is True
    assert defaults["llamacpp"]["args"] == "--no-mmap"
    dropin = NO_REMOTE_FETCH_DROPIN.read_text()
    assert f"Environment=HF_ENDPOINT={BLACKHOLE_ENDPOINT}" in dropin
    assert f"Environment=MODEL_ENDPOINT={BLACKHOLE_ENDPOINT}" in dropin
    assert not (PKG_ROOT / "usr/share/metainfo").exists()
    assert "backup = etc/lemonade/conf.d/zz-secrets.conf" in PKGINFO.read_text()


def test_prepared_source_contains_zerank_selected_logit_adapter():
    if not SOURCE_TREE.exists():
        pytest.skip("prepared lemonade source is not present")

    server_models = SOURCE_TREE / "src/cpp/resources/server_models.json"
    adapter = SOURCE_TREE / "src/cpp/server/backends/llamacpp_reranking_adapter.cpp"
    adapter_header = (
        SOURCE_TREE / "src/cpp/include/lemon/backends/llamacpp_reranking_adapter.h"
    )
    missing_paths = [path for path in (server_models, adapter, adapter_header) if not path.exists()]
    if missing_paths:
        pytest.fail(
            "prepared lemonade source is incomplete; missing "
            + ", ".join(str(path) for path in missing_paths)
        )

    models_text = server_models.read_text()
    adapter_text = adapter.read_text()
    header_text = adapter_header.read_text()

    assert '"zerank-2-GGUF"' in models_text
    assert '"llamacpp_reranking_adapter": "zeroentropy-logit-score"' in models_text
    assert '"llamacpp_reranking_true_token_id": 9454' in models_text
    assert '"llamacpp_reranking_logit_scale": 5.0' in models_text
    assert "ZEROENTROPY_LOGIT_SCORE_ADAPTER" in header_text
    assert "token_logits" in adapter_text


def test_pkgbuild_declares_runtime_library_depends():
    # Owning packages of lemond's DT_NEEDED libraries, as namcap maps them.
    text = PKGBUILD.read_text()
    match = re.search(r"^depends=\(([^)]*)\)", text, re.MULTILINE)
    assert match is not None
    assert set(match.group(1).split()) == {
        "brotli",
        "curl",
        "glibc",
        "libcap",
        "libdrm",
        "libgcc",
        "libstdc++",
        "libwebsockets",
        "systemd-libs",
        "zlib",
        "zstd",
    }
