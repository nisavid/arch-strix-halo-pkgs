import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_DIR = REPO_ROOT / "packages/kokoros-gfx1151"
PKGBUILD = PACKAGE_DIR / "PKGBUILD"
RECIPE_JSON = PACKAGE_DIR / "recipe.json"
README = PACKAGE_DIR / "README.md"

# lemonade-sdk/Kokoros b17, the kokoro.cpu release that Lemonade b6616eb3 pins.
EXPECTED_VERSION = "b17"
EXPECTED_COMMIT = "d122b52e0ee0a90df26fd041620af36f99e2248a"
EXPECTED_ARCHIVE_SHA256 = "2bcc95b4b1a7e0ff1f985e7c684d65df52a955ae66dcd601d0c1e3205daae4fd"
EXPECTED_CARGO_LOCK_SHA256 = "d3cd1b8abd00b49cb5fd07f4e6cd415f6d224655e878b738c7cb3a7e2bb938cc"
INSTALL_ROOT = "/opt/kokoros-gfx1151"


def _array(text, key):
    match = re.search(rf"^{key}=\((.*)\)$", text, re.MULTILINE)
    assert match, f"{key} not found"
    return match.group(1).split()


def _function(text, name):
    start = text.index(f"{name}() {{")
    end = text.index("\n}\n", start)
    return text[start:end]


def test_pkgbuild_pins_the_kokoros_source_archive_and_lockfile():
    text = PKGBUILD.read_text()
    assert re.search(rf"^pkgver={EXPECTED_VERSION}$", text, re.MULTILINE)
    assert _array(text, "source") == [
        f"Kokoros-{EXPECTED_COMMIT}.tar.gz::https://github.com/lemonade-sdk/Kokoros/archive/{EXPECTED_COMMIT}.tar.gz"
    ]
    assert _array(text, "sha256sums") == [EXPECTED_ARCHIVE_SHA256]
    prepare = _function(text, "prepare")
    assert f"'{EXPECTED_CARGO_LOCK_SHA256}' | sha256sum --check --quiet -" in prepare
    assert prepare.index("sha256sum --check") < prepare.index("cargo fetch --locked")
    assert 'cargo fetch --locked --target "$(rustc --print host-tuple)"' in prepare


def test_build_is_frozen_offline_and_never_downloads_onnxruntime_or_sonic():
    text = PKGBUILD.read_text()
    build = _function(text, "build")
    for line in (
        'export XDG_CACHE_HOME="$srcdir/.cache"',
        "export ORT_LIB_LOCATION=/usr/lib",
        "export ORT_PREFER_DYNAMIC_LINK=1",
        "export ORT_SKIP_DOWNLOAD=1",
        "export CARGO_NET_OFFLINE=true",
        "export LIBOPUS_LIB_DIR=/usr/lib",
    ):
        assert line in build
    assert "-C link-arg=-lsonic" in build
    assert build.index("export ORT_LIB_LOCATION") < build.index("cargo build")
    assert "cargo build --frozen --offline --release -p koko" in build
    # The system libraries replace ort-sys's download, audiopus_sys's bundled
    # opus, and espeak-ng's sonic clone.
    for dependency in ("libsonic", "onnxruntime-cpu", "openssl", "opus"):
        assert dependency in _array(text, "depends")
    for dependency in ("cargo", "clang", "cmake", "libsonic", "pkgconf", "rust"):
        assert dependency in _array(text, "makedepends")


def test_check_fails_closed_on_network_fetches_and_wrong_linkage():
    check = _function(PKGBUILD.read_text(), "check")
    assert 'find "$srcdir" -type d -name dfbin' in check
    assert "-path '*/_deps/sonic-git*'" in check
    assert "readelf -d" in check
    assert "for _lib in libonnxruntime.so libopus.so libsonic.so; do" in check
    assert check.count("return 1") == 3


def test_package_installs_koko_beside_espeak_ng_data_under_opt():
    package = _function(PKGBUILD.read_text(), "package")
    assert f'local _root="$pkgdir{INSTALL_ROOT}"' in package
    assert 'install -Dm755 "$srcdir/target/release/koko" "${_root}/koko"' in package
    assert 'cp -r --no-preserve=ownership espeak-ng-data "${_root}/espeak-ng-data"' in package
    assert "/usr/bin" not in package
    # Model and voice files belong to #107's model contract.
    assert ".onnx" not in package
    assert "voices" not in package


def test_package_installs_the_available_licence_texts():
    text = PKGBUILD.read_text()
    package = _function(text, "package")
    assert 'install -Dm644 README.md "${_licenses}/README.md"' in package
    assert "cargo tree --frozen --offline" in package
    assert "-e normal" in package
    assert "mp3lame-sys-*/lame-*/COPYING" in package
    assert _array(text, "license") == [
        "Apache-2.0",
        "GPL-3.0-or-later",
        "MIT",
        "ISC",
        "LGPL-2.0-or-later",
        "BSD-3-Clause",
        "LGPL-3.0-only",
        "Unicode-3.0",
    ]


def test_recipe_records_no_reference_and_the_open_runtime_gates():
    recipe = json.loads(RECIPE_JSON.read_text())
    assert recipe["role"] == "tts-runtime"
    assert recipe["maintenance"]["authoritative_reference"] == "none"
    assert recipe["maintenance"]["advisory_references"] == []
    assert recipe["policy"]["upstream_revision"] == EXPECTED_COMMIT
    assert recipe["policy"]["cargo_lock_sha256"] == EXPECTED_CARGO_LOCK_SHA256
    notes = " ".join(recipe["maintenance"]["update_notes"])
    assert "untested" in notes and "installed smoke test must prove" in notes
    assert "confirmed only at build time" in notes
    assert "kokoro-v1.0.onnx" in notes and "voices-v1.0.bin" in notes and "#107" in notes
    readme = README.read_text()
    assert "kokoro-v1.0.onnx and voices-v1.0.bin" in readme
    assert "C API version 23" in readme
