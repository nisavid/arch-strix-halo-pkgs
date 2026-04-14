from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-amd-aiter-gfx1151/PKGBUILD"
RUNTIME_PATCH = (
    REPO_ROOT
    / "packages/python-amd-aiter-gfx1151/0002-jit-runtime-finds-hipcc-and-user-jit-modules.patch"
)


def test_pkgbuild_carries_jit_runtime_patch():
    text = PKGBUILD.read_text()

    assert "pkgrel=2" in text
    assert RUNTIME_PATCH.name in text
    assert f'patch -Np1 -i "$srcdir/{RUNTIME_PATCH.name}"' in text
    assert 'export PATH="/opt/rocm/bin:${PATH}"' in text
    assert 'export ROCM_HOME="/opt/rocm"' in text
    assert 'export HIP_PATH="/opt/rocm"' in text


def test_runtime_patch_fixes_user_jit_import_and_hipcc_resolution():
    text = RUNTIME_PATCH.read_text()

    assert "if home_jit_dir not in sys.path:" in text
    assert "def get_hipcc_path() -> str:" in text
    assert '"/opt/rocm/bin/hipcc"' in text
    assert '[get_hipcc_path()]' in text
    assert 'or user_jit_dir != this_dir' in text
    assert 'importlib.import_module(md_name)' in text
