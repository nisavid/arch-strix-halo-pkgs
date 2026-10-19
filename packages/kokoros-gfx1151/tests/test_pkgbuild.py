import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


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
FAIL_CLOSED_PATCH = "0001-koko-fail-closed-on-missing-model-files.patch"


def _load_renderer():
    tools = REPO_ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    spec = importlib.util.spec_from_file_location("kokoros_test_renderer", tools / "render_recipe_scaffolds.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# prepare()'s guard and the patch target come from the same renderer constant.
MODEL_FETCH_SOURCE = _load_renderer().KOKOROS_MODEL_FETCH_SOURCE


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
    assert _array(text, "source")[0] == (
        f"Kokoros-{EXPECTED_COMMIT}.tar.gz::https://github.com/lemonade-sdk/Kokoros/archive/{EXPECTED_COMMIT}.tar.gz"
    )
    assert _array(text, "sha256sums")[0] == EXPECTED_ARCHIVE_SHA256
    prepare = _function(text, "prepare")
    assert f"'{EXPECTED_CARGO_LOCK_SHA256}' | sha256sum --check --quiet -" in prepare
    assert prepare.index("sha256sum --check") < prepare.index("cargo fetch --locked")
    assert 'cargo fetch --locked --target "$(rustc --print host-tuple)"' in prepare


def test_fail_closed_model_patch_is_listed_checksummed_and_applied():
    text = PKGBUILD.read_text()
    patch_path = PACKAGE_DIR / FAIL_CLOSED_PATCH
    assert _array(text, "source") == [_array(text, "source")[0], FAIL_CLOSED_PATCH]
    assert _array(text, "sha256sums") == [
        EXPECTED_ARCHIVE_SHA256,
        hashlib.sha256(patch_path.read_bytes()).hexdigest(),
    ]
    recipe = json.loads(RECIPE_JSON.read_text())
    assert recipe["maintenance"]["source_patches"] == [FAIL_CLOSED_PATCH]
    prepare = _function(text, "prepare")
    apply = f'  patch --batch -Np1 -i "$srcdir/{FAIL_CLOSED_PATCH}"'
    assert apply in prepare
    # The patch lands before the lockfile check and the crate fetch, and
    # prepare() refuses a tree where koko can still download.
    sentinel = (
        f"if [[ ! -f {MODEL_FETCH_SOURCE} ]] || grep -q download_file_from_url {MODEL_FETCH_SOURCE}; then"
    )
    assert f'patch --dry-run --batch -R -Np1 -i "$srcdir/{FAIL_CLOSED_PATCH}"' in prepare
    assert prepare.index(apply) < prepare.index(sentinel) < prepare.index("sha256sum --check")
    assert prepare.index("sha256sum --check") < prepare.index("cargo fetch --locked")
    assert "KOKOROS_MODEL_FETCH" in prepare
    assert "return 1" in prepare[prepare.index(sentinel):]


def test_fail_closed_model_patch_replaces_every_download_with_an_error():
    patch = (PACKAGE_DIR / FAIL_CLOSED_PATCH).read_text()
    targets = re.findall(r"^diff --git a/(\S+) b/", patch, re.MULTILINE)
    # Only koko.rs changes; Cargo.toml and Cargo.lock stay untouched, so
    # cargo fetch --locked and cargo build --frozen still hold.
    assert targets == [MODEL_FETCH_SOURCE]
    removed = [line for line in patch.splitlines() if line.startswith("-") and not line.startswith("---")]
    added = [line for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")]
    assert sum("download_file_from_url" in line for line in removed) == 4
    assert not any("download_file_from_url" in line or "reqwest" in line for line in added)
    assert sum("panic!(" in line for line in added) == 4
    assert sum("is missing; this build never downloads it" in line for line in added) == 4


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
    # A separate assignment keeps errexit live; local x=$(...) or a process
    # substitution would hide a cargo tree failure.
    assert '  _tree="$(cargo tree --frozen --offline' in package
    assert "< <(cargo tree" not in package
    assert "KOKOROS_LICENSES: no fetched registry source" in package
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
    assert f"{FAIL_CLOSED_PATCH} removes that fallback" in notes
    assert "absent files fail without egress" in notes
    readme = README.read_text()
    assert "kokoro-v1.0.onnx and voices-v1.0.bin" in readme
    assert "C API version 23" in readme


def _run_package(tmp_path, cargo_tree_script):
    """Run the rendered package() the way makepkg does, with a fake cargo."""
    srcdir = tmp_path / "src"
    pkgdir = tmp_path / "pkg"
    source = srcdir / f"Kokoros-{EXPECTED_COMMIT}"
    (source / "espeak-ng-data").mkdir(parents=True)
    (source / "espeak-ng-data" / "phontab").write_text("data\n")
    (source / "README.md").write_text("Apache\n")
    (srcdir / "target/release").mkdir(parents=True)
    (srcdir / "target/release/koko").write_text("binary\n")
    registry = srcdir / ".cargo/registry/src/index.crates.io-0000000000000000"
    (registry / "foo-1.0.0").mkdir(parents=True)
    (registry / "foo-1.0.0/LICENSE-MIT").write_text("MIT\n")
    (registry / "mp3lame-sys-0.1.9/lame-3.100").mkdir(parents=True)
    (registry / "mp3lame-sys-0.1.9/lame-3.100/COPYING").write_text("LGPL\n")
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    (fakebin / "rustc").write_text("#!/bin/sh\necho x86_64-unknown-linux-gnu\n")
    (fakebin / "cargo").write_text("#!/bin/sh\n" + cargo_tree_script)
    for tool in ("rustc", "cargo"):
        (fakebin / tool).chmod(0o755)
    function = _function(PKGBUILD.read_text(), "package") + "\n}\n"
    (tmp_path / "package.sh").write_text(function)
    script = (
        "set -o errexit -o errtrace\n"
        "trap 'exit 1' ERR\n"
        'source "$1"\n'
        "package\n"
        "echo PACKAGE_OK\n"
    )
    env = {
        "PATH": f"{fakebin}:/usr/bin:/bin",
        "srcdir": str(srcdir),
        "pkgdir": str(pkgdir),
    }
    result = subprocess.run(
        ["bash", "-c", script, "probe", str(tmp_path / "package.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, pkgdir / "usr/share/licenses/kokoros-gfx1151"


def test_package_fails_when_cargo_tree_fails(tmp_path):
    result, _ = _run_package(tmp_path, "exit 101\n")
    assert result.returncode != 0
    assert "PACKAGE_OK" not in result.stdout


def test_package_fails_on_a_crate_without_a_fetched_registry_source(tmp_path):
    result, _ = _run_package(
        tmp_path,
        "echo 'foo v1.0.0'\necho 'gitdep v0.1.0 (https://github.com/example/gitdep?rev=abc#abc)'\n",
    )
    assert result.returncode != 0
    assert "PACKAGE_OK" not in result.stdout
    assert "KOKOROS_LICENSES: no fetched registry source for gitdep v0.1.0" in result.stderr


def test_package_installs_registry_licences_and_skips_workspace_crates(tmp_path):
    result, licenses = _run_package(
        tmp_path,
        "echo 'koko v0.1.0 (/build/koko)'\necho 'foo v1.0.0'\necho 'foo v1.0.0 (*)'\n",
    )
    assert result.returncode == 0, result.stderr
    assert "PACKAGE_OK" in result.stdout
    assert (licenses / "crates/foo-1.0.0/LICENSE-MIT").read_text() == "MIT\n"
    assert (licenses / "crates/mp3lame-sys-0.1.9/lame-3.100-COPYING").is_file()
    assert (licenses / "README.md").is_file()


def _run_prepare(tmp_path, koko_rs, real_patch=False):
    """Run the rendered prepare() the way makepkg does, with fake tools.

    koko_rs is the text of kokoros/src/tts/koko.rs after patching, or None
    when the file is absent. The fake patch changes nothing, so the guard
    sees exactly that text. With real_patch, the system patch applies the
    package's patch file instead, with stdin closed.
    """
    srcdir = tmp_path / "src"
    source = srcdir / f"Kokoros-{EXPECTED_COMMIT}"
    source.mkdir(parents=True)
    if koko_rs is not None:
        (source / MODEL_FETCH_SOURCE).parent.mkdir(parents=True)
        (source / MODEL_FETCH_SOURCE).write_text(koko_rs)
    log = tmp_path / "calls.log"
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    if real_patch:
        shutil.copy(PACKAGE_DIR / FAIL_CLOSED_PATCH, srcdir / FAIL_CLOSED_PATCH)
    fakes = {
        # The reverse dry-run fails, so prepare() applies the patch.
        "patch": f'echo "patch $*" >> "{log}"\ncase " $* " in *" --dry-run "*) exit 1;; esac\nexit 0\n',
        "sha256sum": f'echo "sha256sum $*" >> "{log}"\ncat >/dev/null\nexit 0\n',
        "cargo": f'echo "cargo $*" >> "{log}"\nexit 0\n',
        "rustc": "echo x86_64-unknown-linux-gnu\n",
    }
    if real_patch:
        del fakes["patch"]
    for name, body in fakes.items():
        (fakebin / name).write_text("#!/bin/sh\n" + body)
        (fakebin / name).chmod(0o755)
    function = _function(PKGBUILD.read_text(), "prepare") + "\n}\n"
    (tmp_path / "prepare.sh").write_text(function)
    script = (
        "set -o errexit -o errtrace\n"
        "trap 'exit 1' ERR\n"
        'source "$1"\n'
        "prepare\n"
        "echo PREPARE_OK\n"
    )
    result = subprocess.run(
        ["bash", "-c", script, "probe", str(tmp_path / "prepare.sh")],
        env={"PATH": f"{fakebin}:/usr/bin:/bin", "srcdir": str(srcdir)},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    calls = log.read_text() if log.exists() else ""
    return result, calls


def test_prepare_fails_when_koko_still_calls_the_download_helper(tmp_path):
    result, calls = _run_prepare(
        tmp_path, "utils::fileio::download_file_from_url(cfg.model_url.as_str(), model_path)\n"
    )
    assert result.returncode != 0
    assert "PREPARE_OK" not in result.stdout
    assert "KOKOROS_MODEL_FETCH" in result.stderr
    assert "cargo fetch" not in calls


def test_prepare_fails_when_koko_source_is_missing(tmp_path):
    result, calls = _run_prepare(tmp_path, None)
    assert result.returncode != 0
    assert "PREPARE_OK" not in result.stdout
    assert "KOKOROS_MODEL_FETCH" in result.stderr
    assert "cargo fetch" not in calls


def test_prepare_applies_the_patch_and_fetches_locked_crates(tmp_path):
    result, calls = _run_prepare(tmp_path, 'panic!("model file is missing; this build never downloads it")\n')
    assert result.returncode == 0, result.stderr
    assert "PREPARE_OK" in result.stdout
    lines = calls.splitlines()
    assert lines[0].startswith("patch --dry-run --batch -R -Np1 -i ")
    assert lines[1] == f"patch --batch -Np1 -i {tmp_path}/src/{FAIL_CLOSED_PATCH}"
    assert lines[2] == "sha256sum --check --quiet -"
    assert lines[3] == "cargo fetch --locked --target x86_64-unknown-linux-gnu"


@pytest.mark.skipif(shutil.which("patch") is None, reason="needs the system patch")
def test_prepare_never_prompts_when_a_repin_drops_koko_rs(tmp_path):
    # Both patch calls pass --batch, so a missing target is skipped instead
    # of prompting for a file name, and prepare() still fails closed.
    result, calls = _run_prepare(tmp_path, None, real_patch=True)
    assert result.returncode != 0
    assert "PREPARE_OK" not in result.stdout
    assert "File to patch:" not in result.stdout + result.stderr
    assert "cargo fetch" not in calls
