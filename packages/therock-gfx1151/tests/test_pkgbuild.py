from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/therock-gfx1151/PKGBUILD"
AMDSMI_PKGDIR = REPO_ROOT / "packages/therock-gfx1151/pkg/amdsmi-gfx1151"
AMDSMI_PTH = AMDSMI_PKGDIR / "usr/lib/python3.14/site-packages/amd_smi.pth"


def test_amdsmi_package_exports_python_import_hook():
    text = PKGBUILD.read_text()
    assert "package_amdsmi-gfx1151()" in text
    assert "python-gfx1151" in text
    assert "amd_smi.pth" in text
    assert "/opt/rocm/share/amd_smi" in text


def test_built_amdsmi_package_installs_python_import_hook():
    assert AMDSMI_PTH.exists()
    assert AMDSMI_PTH.read_text().strip() == "/opt/rocm/share/amd_smi"
