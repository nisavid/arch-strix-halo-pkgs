from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/aocl-libm-gfx1151/PKGBUILD"


def test_pkgbuild_uses_system_scons_without_network_bootstrap():
    text = PKGBUILD.read_text()

    assert "makedepends=(git patchelf python rocm-llvm-gfx1151 scons)" in text
    assert "python -m pip install" not in text
    assert ".scons-venv" not in text
    assert 'local amdclang="/opt/rocm/lib/llvm/bin/amdclang"' in text
    assert 'local amdclangxx="/opt/rocm/lib/llvm/bin/amdclang++"' in text
    assert 'local amdclang="$(command -v "$CC")"' not in text
    assert 'cp -a --no-preserve=ownership include/. "$pkgdir/usr/include/"' in text
    assert 'cp -a include/. "$pkgdir/usr/include/"' not in text
    assert 'cp -r --no-preserve=ownership include/. "$pkgdir/usr/include/"' not in text
    assert "scons -j\"$(nproc)\"" in text
