from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/lemonade-app/PKGBUILD"
DESKTOP_FILE = (
    REPO_ROOT
    / "packages/lemonade-app/pkg/lemonade-app/usr/share/applications/lemonade-app.desktop"
)
WRAPPER = REPO_ROOT / "packages/lemonade-app/pkg/lemonade-app/usr/bin/lemonade-app"


def test_pkgbuild_installs_lemonade_app_wrapper():
    text = PKGBUILD.read_text()
    assert 'rm -rf "${build_root}"' in text
    assert "$pkgdir/usr/bin/lemonade-app" in text
    assert "/usr/share/lemonade-app/lemonade" in text


def test_built_package_ships_desktop_launcher_wrapper():
    assert WRAPPER.exists()
    assert WRAPPER.is_file()


def test_desktop_entry_uses_packaged_launcher_name():
    text = DESKTOP_FILE.read_text()
    assert "Exec=lemonade-app" in text
