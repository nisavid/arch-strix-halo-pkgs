from pathlib import Path
import re
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from recipe_policy import load_recipe_policy  # noqa: E402


PKGBUILD = REPO_ROOT / "packages/lemonade-app/PKGBUILD"
SERVER_PKGBUILD = REPO_ROOT / "packages/lemonade-server/PKGBUILD"
RECIPE_POLICY = REPO_ROOT / "policies/recipe-packages.toml"
GLIB_PATCH = (
    REPO_ROOT
    / "packages/lemonade-app/0001-keep-tauri-glib-on-webkit-compatible-series.patch"
)
DESKTOP_FILE = (
    REPO_ROOT
    / "packages/lemonade-app/pkg/lemonade-app/usr/share/applications/lemonade-app.desktop"
)
WRAPPER = REPO_ROOT / "packages/lemonade-app/pkg/lemonade-app/usr/bin/lemonade-app"


def test_pkgbuild_installs_lemonade_app_wrapper():
    text = PKGBUILD.read_text()
    assert "cargo" in text
    assert "rust" in text
    assert 'local _ccache_cache="$srcdir/.ccache/cache"' in text
    assert 'export CCACHE_DIR="${_ccache_cache}"' in text
    assert 'export CARGO_HOME="$srcdir/.cargo"' in text
    assert 'export npm_config_cache="$srcdir/.npm-cache"' in text
    assert 'export RUSTFLAGS="--remap-path-prefix=$srcdir=${_debug_prefix}"' in text
    assert "0001-keep-tauri-glib-on-webkit-compatible-series.patch" in text
    assert "_apply_patch_if_needed()" in text
    assert 'patch --dry-run -R -Np1 -i "${_patch}"' in text
    assert '_apply_patch_if_needed "0001-keep-tauri-glib-on-webkit-compatible-series.patch"' in text
    assert 'rm -rf "${build_root}"' in text
    assert "--target tauri-app" in text
    assert "--target electron-app" not in text
    assert "$pkgdir/usr/bin/lemonade-app" in text
    assert "/usr/share/lemonade-app/lemonade-app" in text


def test_pkgbuild_keeps_tauri_glib_on_webkit_compatible_series():
    text = GLIB_PATCH.read_text()

    assert '-glib = "0.20"' in text
    assert '+glib = "0.18"' in text


def test_pkgbuild_builds_the_same_pinned_fork_commit_as_the_server():
    text = PKGBUILD.read_text()
    pin = load_recipe_policy(RECIPE_POLICY)["source_pins"]["lemonade"]

    assert re.fullmatch(r"[0-9a-f]{40}", pin)
    assert f"'lemonade::git+https://github.com/nisavid/lemonade.git#commit={pin}'" in text
    assert f"#commit={pin}'" in SERVER_PKGBUILD.read_text()
    assert "0002-surface-reranking-server-errors.patch" not in text


def test_pkgbuild_checksums_the_local_patch():
    text = PKGBUILD.read_text()

    assert re.search(r"^sha256sums=\(SKIP [0-9a-f]{64}\)$", text, re.MULTILINE)


def test_built_package_ships_desktop_launcher_wrapper():
    if not WRAPPER.exists():
        pytest.skip("built lemonade-app package image is not present")

    assert WRAPPER.exists()
    assert WRAPPER.is_file()


def test_desktop_entry_uses_packaged_launcher_name():
    if not DESKTOP_FILE.exists():
        pytest.skip("built lemonade-app package image is not present")

    text = DESKTOP_FILE.read_text()
    assert "Exec=lemonade-app" in text
