from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKG_DIR = REPO_ROOT / "packages/python-vllm-rocm-gfx1151"
PATCH = PKG_DIR / "0016-rocm-refresh-local-carry-for-vllm-0.30.0.patch"
PKGBUILD = PKG_DIR / "PKGBUILD"


def test_patch_maps_cuda_bfloat_vector_aliases_for_rocm():
    text = PATCH.read_text()

    assert "diff --git a/csrc/libtorch_stable/cuda_vec_utils.cuh" in text
    assert "diff --git a/csrc/cuda_vec_utils.cuh" not in text
    assert "using vllm_bfloat16 = __hip_bfloat16;" in text
    assert "using vllm_bfloat162 = __hip_bfloat162;" in text
    assert "PackedTypeConverter<vllm_bfloat162>" in text
    assert "c10::BFloat16 -> vllm_bfloat16" in text
    assert "using Type = vllm_bfloat16;" in text


def test_pkgbuild_needs_setuptools_rust_to_import_setup_py():
    text = PKGBUILD.read_text()
    makedepends = text.split("makedepends=(", 1)[1].split(")", 1)[0].split()

    assert "python-setuptools-rust" in makedepends
    assert "rust" not in makedepends
    assert "cargo" not in makedepends


def test_pkgbuild_skips_optional_rust_extensions_and_rejects_them_in_the_wheel():
    text = PKGBUILD.read_text()
    build = text[text.index("build() {") : text.index("package() {")]

    assert "unset VLLM_REQUIRE_RUST_FRONTEND" in build
    assert "export CARGO=/usr/bin/false" in build
    assert "export CARGO_NET_OFFLINE=true" in build
    assert "export RUSTUP_AUTO_INSTALL=0" in build
    assert "cargo fetch" not in text
    assert build.index("export CARGO=/usr/bin/false") < build.index("pip wheel .")
    assert build.index("pip wheel .") < build.index("VLLM_RUST_ARTIFACT_UNEXPECTED")
    assert "grep -Eq '^vllm/(_rust_[^/]*[.]so|vllm-rs)$'" in build


def test_pkgbuild_builds_one_wheel_without_an_aiter_fallback():
    text = PKGBUILD.read_text()

    assert text.count("pip wheel . --no-build-isolation --no-deps --wheel-dir dist -v") == 1
    assert "python setup.py clean" not in text
