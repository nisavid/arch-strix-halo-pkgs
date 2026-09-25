import json
import subprocess
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
DROPPED_ARGS_MERGE_PATCH = (
    REPO_ROOT
    / "packages/lemonade-server/0005-merge-custom-args-without-keeping-quotes.patch"
)
PKG_ROOT = REPO_ROOT / "packages/lemonade-server/pkg/lemonade-server"
LLAMACPP_ENV_TARGET = "/usr/lib/lemonade/llamacpp-gfx1151.env"
LLAMACPP_ENV = PKG_ROOT / LLAMACPP_ENV_TARGET.lstrip("/")
ENV_FILES_DROPIN_TARGET = "/usr/lib/systemd/system/lemond.service.d/30-env-files.conf"
ENV_FILES_DROPIN = PKG_ROOT / ENV_FILES_DROPIN_TARGET.lstrip("/")
ENV_FILE = PKG_ROOT / "etc/default/lemond"
SECRETS_TARGET = "/etc/lemonade/conf.d/zz-secrets.conf"
SECRETS = PKG_ROOT / SECRETS_TARGET.lstrip("/")
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


def _heredoc(text, target, mode="644"):
    match = re.search(
        rf'install -Dm{mode} /dev/stdin "\$pkgdir{re.escape(target)}" <<\'EOF\'\n(.*?)\nEOF\n',
        text,
        re.DOTALL,
    )
    assert match, f"no mode {mode} heredoc install for {target}"
    return match.group(1)


def _assignments(text):
    """The KEY=value lines of an env file or unit drop-in, as (key, value)."""
    return [
        tuple(line.split("=", 1))
        for line in text.splitlines()
        if line and not line.startswith(("#", ";", "["))
    ]


EXPECTED_LLAMACPP_VERSION = _pkgbuild_value(LLAMACPP_HIP_PKGBUILD, "pkgver")
EXPECTED_RELEASE_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/tag/"
    f"{EXPECTED_LLAMACPP_VERSION}"
)
LEMONADE_PIN = load_recipe_policy(RECIPE_POLICY)["source_pins"]["lemonade"]


EXPECTED_ENV_FILES_DROPIN = """\
# lemonade-server owns the whole EnvironmentFile= list of lemond.service.
# systemd reads the files in this order, a later file overrides an earlier
# one, and any EnvironmentFile= value overrides an Environment= value, such
# as the 20-no-remote-model-fetch.conf blackholes.
[Service]
# Clear the list first. systemd keeps a repeated path at its first position,
# so listing upstream's /etc/default/lemond again without this reset would
# not move it after conf.d. The build fails if upstream's unit lists any
# other EnvironmentFile=, which this reset would drop.
EnvironmentFile=
# Optional settings in the pre-11.9 location, including the packaged
# zz-secrets.conf placeholder, read in glob order.
EnvironmentFile=-/etc/lemonade/conf.d/*.conf
# Optional: upstream's env file for HF_TOKEN, LEMONADE_API_KEY, and
# LEMONADE_ADMIN_API_KEY. It overrides conf.d.
EnvironmentFile=-/etc/default/lemond
# Required: the packaged llama.cpp backends, read last so that a stale
# LEMONADE_LLAMACPP_* key in a file above cannot replace them. To override
# one, add an EnvironmentFile= in a drop-in under
# /etc/systemd/system/lemond.service.d/ that sorts after this one; an
# Environment= line cannot, because every env file overrides it.
EnvironmentFile=/usr/lib/lemonade/llamacpp-gfx1151.env"""


def test_pkgbuild_owns_the_service_environment_file_order_in_one_drop_in():
    assert _heredoc(PKGBUILD.read_text(), ENV_FILES_DROPIN_TARGET) == EXPECTED_ENV_FILES_DROPIN


def test_pkgbuild_ships_the_llamacpp_backends_as_a_package_env_file():
    # lemond reads LEMONADE_LLAMACPP_*_BIN from its environment ahead of
    # config.json, and patch 0004 reads the version and release URL only from
    # the environment.
    text = _heredoc(PKGBUILD.read_text(), LLAMACPP_ENV_TARGET)
    assert _assignments(text) == [
        ("LEMONADE_LLAMACPP_ROCM_BIN", HIP_SERVER),
        ("LEMONADE_LLAMACPP_VULKAN_BIN", VULKAN_SERVER),
        ("LEMONADE_LLAMACPP_ROCM_VERSION", EXPECTED_LLAMACPP_VERSION),
        ("LEMONADE_LLAMACPP_VULKAN_VERSION", EXPECTED_LLAMACPP_VERSION),
        ("LEMONADE_LLAMACPP_ROCM_RELEASE_URL", EXPECTED_RELEASE_URL),
        ("LEMONADE_LLAMACPP_VULKAN_RELEASE_URL", EXPECTED_RELEASE_URL),
    ]


def test_pkgbuild_ships_only_the_env_files_and_blackhole_drop_ins():
    text = PKGBUILD.read_text()
    assert re.findall(r'"\$pkgdir/usr/lib/systemd/system/lemond\.service\.d/([^"]+)"', text) == [
        "20-no-remote-model-fetch.conf",
        "30-env-files.conf",
    ]
    assert "10-llamacpp-gfx1151.conf" not in text


def test_pkgbuild_keeps_the_legacy_secrets_placeholder_private():
    # Byte-identical to the 11.7 placeholder, so pacman leaves an
    # owner-edited copy in place instead of writing a .pacnew; the conf.d
    # glob keeps loading it. A .pacsave would not match that glob.
    assert _heredoc(PKGBUILD.read_text(), SECRETS_TARGET, mode="660") == (
        "# Installed as /etc/lemonade/conf.d/zz-secrets.conf so it loads after other\n"
        "# drop-ins and keeps secrets separate from the base config file.\n"
        "#LEMONADE_API_KEY="
    )


def test_pkgbuild_drop_ins_keep_the_config_and_cache_split():
    # A cache-dir argument, LEMONADE_CACHE_DIR, HOME, or XDG_* override would
    # make lemond's config dir follow the cache dir.
    text = PKGBUILD.read_text()
    for target in (
        LLAMACPP_ENV_TARGET,
        ENV_FILES_DROPIN_TARGET,
        "/usr/lib/systemd/system/lemond.service.d/20-no-remote-model-fetch.conf",
    ):
        dropin = _heredoc(text, target)
        assert "ExecStart" not in dropin
        for key, _ in _assignments(dropin):
            assert key not in ("LEMONADE_CACHE_DIR", "HOME")
            assert not key.startswith("XDG_")


def test_pkgbuild_keeps_upstream_lemond_service_install():
    text = PKGBUILD.read_text()
    assert "DESTDIR=\"$pkgdir\" cmake --install" in text
    assert "lemonade-server.service" not in text


def test_pkgbuild_preserves_both_secrets_files_across_upgrades():
    text = PKGBUILD.read_text()

    assert "backup=(etc/default/lemond etc/lemonade/conf.d/zz-secrets.conf)\n" in text


def test_pkgbuild_writes_no_owner_config_from_a_scriptlet():
    assert not re.search(r"^install=", PKGBUILD.read_text(), re.MULTILINE)
    assert not list(PKGBUILD.parent.glob("*.install"))


def test_pkgbuild_checks_the_upstream_unit_layout_after_install():
    text = PKGBUILD.read_text()
    package = text[text.index("package() {"):]

    assert "_check_lemond_unit() {" in package
    assert '_check_lemond_unit "$pkgdir/usr/lib/systemd/system/lemond.service"' in package
    assert package.index("cmake --install") < package.index('_check_lemond_unit "$pkgdir')
    # The check rejects any upstream lemond.service.d drop-in, so it must run
    # before the package installs its own.
    for dropin in sorted(set(re.findall(r'"\$pkgdir(/usr/lib/systemd/system/lemond\.service\.d/[^"]+)"', package))):
        assert package.index('_check_lemond_unit "$pkgdir') < package.index(dropin), dropin
    assert package.index('_check_lemond_unit "$pkgdir') < package.index(ENV_FILES_DROPIN_TARGET)


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
        "auto_update_models": False,
        "max_loaded_models": -1,
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
    local_patches = sorted(PKGBUILD.parent.glob("*.patch"))

    assert sums[0] == "SKIP"
    assert len(sums) == 1 + len(local_patches) == 5
    assert all(re.fullmatch(r"[0-9a-f]{64}", item) for item in sums[1:])


def _prepare_patch_order():
    text = PKGBUILD.read_text()
    prepare = re.search(r"^prepare\(\) \{\n(.*?)^\}", text, re.DOTALL | re.MULTILINE)
    assert prepare, "PKGBUILD has no prepare()"
    return re.findall(r'patch -Np1 -i "\$srcdir/([^"]+)"', prepare.group(1))


def test_pkgbuild_applies_the_carried_patch_series_in_order():
    assert _prepare_patch_order() == [
        "0001-linux-npu-fallback-to-pci-id-when-accel-open-fails.patch",
        "0002-llamacpp-external-backends-are-system-managed.patch",
        "0003-remove-llamacpp-system-backend.patch",
        "0004-system-managed-llamacpp-metadata.patch",
    ]


def test_pkgbuild_drops_the_args_merge_stopgap():
    # The fork fix for the double-quoted custom args (nisavid/lemonade#168) is
    # in the pinned v11.9.0 sync commit, so patch 0005 is gone for good.
    assert not DROPPED_ARGS_MERGE_PATCH.exists()
    assert DROPPED_ARGS_MERGE_PATCH.name not in PKGBUILD.read_text()


def test_pkgbuild_packages_the_synced_upstream_version():
    assert _pkgbuild_value(PKGBUILD, "pkgver") == "11.9.0"
    assert _pkgbuild_value(PKGBUILD, "pkgrel") == "1"


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

    assert ENV_FILES_DROPIN.read_text().rstrip("\n") == EXPECTED_ENV_FILES_DROPIN
    text = LLAMACPP_ENV.read_text()
    assert f"LEMONADE_LLAMACPP_ROCM_VERSION={EXPECTED_LLAMACPP_VERSION}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_VERSION={EXPECTED_LLAMACPP_VERSION}" in text
    assert f"LEMONADE_LLAMACPP_ROCM_RELEASE_URL={EXPECTED_RELEASE_URL}" in text
    assert f"LEMONADE_LLAMACPP_VULKAN_RELEASE_URL={EXPECTED_RELEASE_URL}" in text


def test_built_package_installs_renamed_lemond_service():
    _require_current_package_image()

    assert SERVICE.exists()
    assert not OLD_SERVICE.exists()


def test_built_package_unit_splits_config_and_cache():
    _require_current_package_image()

    lines = SERVICE.read_text().splitlines()
    assert "StateDirectory=lemonade" in lines
    assert "CacheDirectory=lemonade" in lines
    assert "CacheDirectoryMode=0755" in lines
    assert "EnvironmentFile=-/etc/default/lemond" in lines
    assert [line for line in lines if line.startswith("ExecStart=")] == [
        "ExecStart=/usr/bin/lemond"
    ]


def test_built_package_ships_the_secrets_env_file_private():
    _require_current_package_image()

    assert ENV_FILE.stat().st_mode & 0o777 == 0o640
    assert SECRETS.stat().st_mode & 0o777 == 0o660
    pkginfo = PKGINFO.read_text()
    assert "backup = etc/default/lemond" in pkginfo
    assert "backup = etc/lemonade/conf.d/zz-secrets.conf" in pkginfo


def test_built_package_installs_offline_defaults_and_endpoint_drop_in():
    _require_current_package_image()

    defaults = json.loads(DISTRO_DEFAULTS.read_text())
    assert defaults["offline"] is True
    assert defaults["no_fetch_executables"] is True
    assert defaults["llamacpp"]["args"] == "--no-mmap"
    assert defaults["max_loaded_models"] == -1
    assert defaults["auto_update_models"] is False
    dropin = NO_REMOTE_FETCH_DROPIN.read_text()
    assert f"Environment=HF_ENDPOINT={BLACKHOLE_ENDPOINT}" in dropin
    assert f"Environment=MODEL_ENDPOINT={BLACKHOLE_ENDPOINT}" in dropin
    assert not (PKG_ROOT / "usr/share/metainfo").exists()


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


def _rendered_lemond_unit_check():
    """The _check_lemond_unit definition exactly as package() declares it."""
    match = re.search(
        r"^(  _check_lemond_unit\(\) \{\n.*?^  \}\n)", PKGBUILD.read_text(), re.DOTALL | re.MULTILINE
    )
    assert match, "no _check_lemond_unit definition in PKGBUILD"
    return match.group(1)


def _run_lemond_unit_check_like_makepkg(unit_path):
    # makepkg runs package() with errexit and errtrace on and an ERR trap that
    # aborts the build with "A failure occurred in package()"; mirror that.
    script = (
        "shopt -o -s errexit errtrace\n"
        "trap 'echo MAKEPKG_ERR_TRAP >&2; exit 4' ERR\n"
        "package() {\n"
        + _rendered_lemond_unit_check()
        + '  _check_lemond_unit "$1"\n'
        "  echo PACKAGE_CONTINUED\n"
        "}\n"
        "package \"$1\"\n"
    )
    return subprocess.run(
        ["bash", "-c", script, "bash", str(unit_path)],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )


LEMOND_UNIT_EXPECTED = """\
[Unit]
Description=Lemonade Server

[Service]
StateDirectory=lemonade
CacheDirectory=lemonade
CacheDirectoryMode=0755
EnvironmentFile=-/etc/default/lemond
ExecStart=/usr/bin/lemond

[Install]
WantedBy=multi-user.target
"""


def test_unit_check_passes_under_makepkg_errexit_without_a_drop_in_dir(tmp_path):
    # Upstream installs lemond.service and no lemond.service.d directory.
    unit = tmp_path / "lemond.service"
    unit.write_text(LEMOND_UNIT_EXPECTED)

    result = _run_lemond_unit_check_like_makepkg(unit)

    assert result.returncode == 0, result.stderr
    assert "PACKAGE_CONTINUED" in result.stdout
    assert "MAKEPKG_ERR_TRAP" not in result.stderr


def test_unit_check_passes_under_makepkg_errexit_with_an_empty_drop_in_dir(tmp_path):
    unit = tmp_path / "lemond.service"
    unit.write_text(LEMOND_UNIT_EXPECTED)
    (tmp_path / "lemond.service.d").mkdir()

    result = _run_lemond_unit_check_like_makepkg(unit)

    assert result.returncode == 0, result.stderr
    assert "PACKAGE_CONTINUED" in result.stdout


def test_unit_check_fails_under_makepkg_errexit_on_an_upstream_drop_in(tmp_path):
    unit = tmp_path / "lemond.service"
    unit.write_text(LEMOND_UNIT_EXPECTED)
    (tmp_path / "lemond.service.d").mkdir()
    (tmp_path / "lemond.service.d" / "10-upstream.conf").write_text(
        "[Service]\nEnvironmentFile=-/etc/lemonade/extra.env\n"
    )

    result = _run_lemond_unit_check_like_makepkg(unit)

    assert result.returncode != 0
    assert "PACKAGE_CONTINUED" not in result.stdout
    assert "LEMOND_UNIT_LAYOUT: upstream installs" in result.stderr
    assert "10-upstream.conf" in result.stderr


@pytest.mark.parametrize(
    ("unit", "message"),
    [
        (
            LEMOND_UNIT_EXPECTED.replace("CacheDirectory=lemonade\n", ""),
            "lacks CacheDirectory=lemonade",
        ),
        (
            LEMOND_UNIT_EXPECTED.replace("EnvironmentFile=-/etc/default/lemond\n", ""),
            "lacks EnvironmentFile=-/etc/default/lemond",
        ),
        (
            LEMOND_UNIT_EXPECTED.replace("ExecStart=/usr/bin/lemond\n", ""),
            "lacks ExecStart=/usr/bin/lemond",
        ),
        (
            LEMOND_UNIT_EXPECTED.replace(
                "ExecStart=/usr/bin/lemond\n",
                "ExecStart=/usr/bin/lemond\nExecStart = /usr/bin/lemond /var/cache/lemonade\n",
            ),
            "overrides lemond's config or cache dir",
        ),
        (
            LEMOND_UNIT_EXPECTED.replace(
                "ExecStart=/usr/bin/lemond\n",
                "ExecStart=/usr/bin/lemond\nEnvironment=HOME=/srv/lemonade\n",
            ),
            "overrides lemond's config or cache dir",
        ),
        (
            LEMOND_UNIT_EXPECTED.replace(
                "ExecStart=/usr/bin/lemond\n",
                "ExecStart=/usr/bin/lemond\nEnvironmentFile=-/etc/lemonade/extra.env\n",
            ),
            "lists an EnvironmentFile= that 30-env-files.conf would drop",
        ),
    ],
)
def test_unit_check_fails_under_makepkg_errexit_on_a_changed_unit(tmp_path, unit, message):
    unit_path = tmp_path / "lemond.service"
    unit_path.write_text(unit)

    result = _run_lemond_unit_check_like_makepkg(unit_path)

    assert result.returncode != 0
    assert "PACKAGE_CONTINUED" not in result.stdout
    assert f"LEMOND_UNIT_LAYOUT: {unit_path} {message}" in result.stderr
